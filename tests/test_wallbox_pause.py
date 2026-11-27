"""Wallbox may pause as the last measure (BETA, default off, release 0.16.0): python -m unittest discover -s tests

Wish of a user (23.11.2026): "switch the wallbox off completely when lowering the current is not enough". Draft in the house
automation repository (docs/ENTWURF_WALLBOX_PAUSIEREN.md). Rules:
- only with the device switch *may be paused as the last measure* (default off; an older device without the field = off),
- only when the wallbox charges at its minimum current already (a 3-phase one with phase switching first on 1 phase), every other
  lever is used up (switches, battery, settings), and that lasted PAUSE_AFTER_S,
- never in observe mode or with *Observe only* at the device: only the line "would be paused",
- the evcc mode from before is remembered (also over a restart) and put back; given back first (reverse order), only with room for
  the minimum current plus a margin, after the *minimum duration*; no new pause within the *pause after taking back*,
- a mode someone changed meanwhile stays theirs.
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import timedelta

from sim import START, engine

D, R = engine.DeviceConfig, engine.Reading
LIMIT, MARGIN = 10.0, 0.5          # target 9.5 kW
V1 = 230.0


def wb(**kw):
    base = dict(id="wb", name="Wallbox", kind="wallbox", priority=1, min_current=6, max_current=16, may_pause=True)
    base.update(kw)
    return D(**base)


class Car:
    """A wallbox with a car that follows the commands: current, phases, pause (evcc mode off) and allow again."""

    def __init__(self, current=6, phases=3, mode="pv", one_phase_option=None):
        self.current, self.phases, self.mode = current, phases, mode
        self.one_phase_option = one_phase_option
        self.calls: list[tuple[str, object]] = []

    @property
    def kw(self) -> float:
        return 0.0 if self.mode == "off" else self.current * V1 * self.phases / 1000.0

    def reading(self) -> R:
        opt = self.one_phase_option if self.phases == 1 and self.one_phase_option else "Auto"
        return R(power_w=self.kw * 1000.0, current_a=self.current, phases=self.phases, phase_option=opt, mode=self.mode,
                 paused=self.mode == "off")

    def apply(self, a) -> None:
        if a.device_id != "wb" or a.kind == "log":
            return
        self.calls.append((a.kind, a.value))
        if a.kind == "set_current":
            self.current = int(a.value)
        elif a.kind == "set_phase":
            self.phases = 1 if a.value == self.one_phase_option else 3
        elif a.kind == "wb_pause":
            self.mode = "off"
        elif a.kind == "wb_resume":
            self.mode = a.value or "pv"


class House:
    """The base load of the house (a function of the minute) plus the car, a pool pump and an optional battery and setting."""

    def __init__(self, car: Car, base=8.0, pool=False, battery=False, setting=False):
        self.car, self.base = car, base
        self.pool_on, self.has_battery, self.bat_released = pool, battery, False
        self.has_setting, self.set_released = setting, False

    def grid(self, t_min: float) -> float:
        base = self.base(t_min) if callable(self.base) else self.base
        return (base + self.car.kw + (0.75 if self.pool_on else 0.0) - (2.0 if self.bat_released else 0.0)
                - (1.5 if self.set_released else 0.0))

    def readings(self) -> dict:
        out = {"wb": self.car.reading(), "pool": R(power_w=750.0 if self.pool_on else 0.0, is_on=self.pool_on)}
        if self.has_battery:
            out["bat"] = R(soc=80.0, releasable=not self.bat_released)
        if self.has_setting:
            out["wp"] = R(releasable=not self.set_released, power_w=1500.0)
        return out

    def apply(self, a) -> None:
        self.car.apply(a)
        if a.device_id == "pool" and a.kind in ("turn_off", "turn_on"):
            self.pool_on = a.kind == "turn_on"
        elif a.device_id == "bat" and a.kind in ("battery_release", "battery_restore"):
            self.bat_released = a.kind == "battery_release"
        elif a.device_id == "wp" and a.kind in ("battery_release", "battery_restore"):
            self.set_released = a.kind == "battery_release"


def others(battery=False, setting=False):
    out = [D(id="pool", name="Pool", kind="switch", priority=2, min_power_w=150)]
    if battery:
        out.append(D(id="bat", name="Speicher", kind="battery", priority=10, power_w=2000, min_soc=30))
    if setting:
        out.append(D(id="wp", name="Waermepumpe", kind="setting", priority=5, power_w=1500))
    return out


def drive(guard, house: House, minutes: float, t0=START, real=True):
    """Every 20 s one cycle; returns [(minute, action)] of everything the guard returned."""
    out = []
    guard.real_effect = real
    for i in range(int(minutes * 3)):
        t_min = i / 3.0
        now = t0 + timedelta(minutes=t_min)
        acts = guard.step(now, house.grid(t_min), None, house.readings(), LIMIT, MARGIN, True)
        for a in acts:
            out.append((t_min, a))
            if real:
                house.apply(a)
    return out


def kinds(out, kind):
    return [(t, a) for t, a in out if a.kind == kind]


def texts(out):
    return "\n".join(a.text for _, a in out if a.text)


class FieldTests(unittest.TestCase):
    def test_default_off_and_an_older_device_without_the_field(self):
        self.assertFalse(D.from_dict({"id": "x", "kind": "wallbox"}).may_pause)
        self.assertFalse(D.from_dict({"id": "x", "kind": "wallbox", "may_pause": False}).may_pause)
        self.assertTrue(D.from_dict({"id": "x", "kind": "wallbox", "may_pause": True}).may_pause)

    def test_the_new_reading_fields_default_to_unknown(self):
        r = R()
        self.assertIsNone(r.mode)
        self.assertIsNone(r.paused)


class EvccModeKnownTests(unittest.TestCase):
    """Review 27.11.2026: an evcc loadpoint is paused only with a known mode, else there would be no way back."""

    def _run(self, mode, real=True):
        house = House(Car(mode=mode))
        orig = house.readings
        house.readings = lambda: {**orig(), "wb": replace(house.car.reading(), mode=mode, paused=False)}
        guard = engine.Guard([wb(pause_by_mode=True)] + others())
        return drive(guard, house, 10, real=real)

    def test_field_default_and_from_settings(self):
        self.assertFalse(D.from_dict({"id": "x", "kind": "wallbox"}).pause_by_mode)
        self.assertTrue(D.from_dict({"id": "x", "kind": "wallbox", "pause_by_mode": True}).pause_by_mode)

    def test_unknown_mode_no_pause(self):
        out = self._run(None)
        self.assertEqual(kinds(out, "wb_pause"), [], texts(out))

    def test_known_mode_pauses(self):
        self.assertTrue(kinds(self._run("pv"), "wb_pause"))

    def test_observe_mode_no_line_without_a_known_mode(self):
        self.assertFalse([a for _, a in self._run(None, real=False) if "würde pausiert" in a.text])
        self.assertTrue([a for _, a in self._run("pv", real=False) if "würde pausiert" in a.text])

    def test_other_wallbox_without_mode_unchanged(self):
        house = House(Car())
        orig = house.readings
        house.readings = lambda: {**orig(), "wb": replace(house.car.reading(), mode=None)}
        out = drive(engine.Guard([wb()] + others()), house, 10)
        self.assertTrue(kinds(out, "wb_pause"), "a wallbox with its own commands needs no mode")


class WhenTests(unittest.TestCase):
    def test_switch_off_never_pauses(self):
        house = House(Car())
        out = drive(engine.Guard([wb(may_pause=False)] + others()), house, 30)
        self.assertEqual(kinds(out, "wb_pause"), [])
        self.assertEqual(house.car.mode, "pv")

    def test_switch_off_is_exactly_the_behaviour_of_before(self):
        def run(may):
            house = House(Car(current=16), base=lambda t: 8.0 if t < 12 else 3.0, pool=True)
            dev = wb(may_pause=may) if may is not None else D(id="wb", name="Wallbox", kind="wallbox", priority=1)
            return [(t, a.kind, a.value, a.text) for t, a in drive(engine.Guard([dev] + others()), house, 40)]
        old = run(None)   # a device as before 0.16.0, without the field
        self.assertEqual(run(False), old)
        self.assertFalse(any(k in ("wb_pause", "wb_resume") for _, k, _, _ in old))

    def test_pauses_at_the_minimum_after_two_minutes(self):
        house = House(Car())
        guard = engine.Guard([wb()] + others())
        out = drive(guard, house, 6)
        pauses = kinds(out, "wb_pause")
        self.assertEqual(len(pauses), 1, texts(out))
        t, a = pauses[0]
        self.assertGreaterEqual(t, engine.PAUSE_AFTER_S / 60.0 - 1e-9, "not at once: a cooker may only cycle")
        self.assertLess(t, engine.PAUSE_AFTER_S / 60.0 + 1.0)
        self.assertTrue(a.intervention, "counts as an intervention")
        self.assertIn("pausiert", a.text)
        self.assertIn("Mindeststrom reicht nicht", a.text)
        self.assertEqual(guard.interventions["wb"]["paused"]["mode"], "pv", "the mode from before is remembered")
        self.assertEqual(house.car.mode, "off")

    def test_never_while_the_current_can_still_be_lowered(self):
        house = House(Car(current=16))
        guard = engine.Guard([wb()] + others())
        out = drive(guard, house, 0.4)   # the first two cycles
        real = [a for _, a in out if a.kind != "log"]
        self.assertEqual(real[0].kind, "set_current", texts(out))
        self.assertEqual(kinds(out, "wb_pause"), [])

    def test_after_lowering_to_the_minimum_it_pauses_later(self):
        house = House(Car(current=16), base=9.0)
        out = drive(engine.Guard([wb()] + others()), house, 10)
        first_cur = kinds(out, "set_current")[0][0]
        pause = kinds(out, "wb_pause")
        self.assertTrue(pause, texts(out))
        self.assertGreater(pause[0][0], first_cur)
        self.assertEqual(house.car.current, 6, "never below the minimum")

    def test_not_while_the_car_does_not_charge(self):
        house = House(Car(mode="off"))
        out = drive(engine.Guard([wb()] + others()), house, 10)
        self.assertEqual(kinds(out, "wb_pause"), [])

    def test_the_condition_entity_says_no(self):
        house = House(Car())
        guard = engine.Guard([wb()] + others())
        house.readings_orig = house.readings
        house.readings = lambda: {**house.readings_orig(), "wb": replace(house.car.reading(), allowed=False)}
        out = drive(guard, house, 10)
        self.assertEqual(kinds(out, "wb_pause"), [])

    def test_a_short_peak_does_not_pause(self):
        """Too much for 100 s only: no pause."""
        house = House(Car(), base=lambda t: 8.0 if t < 1.6 else 2.0)
        out = drive(engine.Guard([wb()] + others()), house, 10)
        self.assertEqual(kinds(out, "wb_pause"), [])


class OrderTests(unittest.TestCase):
    def _order(self, strategy):
        house = House(Car(), base=10.0, pool=True, battery=True, setting=True)
        guard = engine.Guard([wb()] + others(battery=True, setting=True), strategy)
        out = drive(guard, house, 15)
        firsts = {}
        for t, a in out:
            if a.intervention and a.kind != "log":
                firsts.setdefault(a.device_id, t)
        return firsts, out

    def test_every_other_lever_first_strict_order(self):
        firsts, out = self._order(engine.STRATEGY_ORDER)
        self.assertIn("wb", firsts, texts(out))
        for dev in ("pool", "bat", "wp"):
            self.assertLess(firsts[dev], firsts["wb"], (dev, texts(out)))

    def test_every_other_lever_first_comfort(self):
        firsts, out = self._order(engine.STRATEGY_COMFORT)
        self.assertIn("wb", firsts, texts(out))
        for dev in ("pool", "bat", "wp"):
            self.assertLess(firsts[dev], firsts["wb"], (dev, texts(out)))

    def test_a_second_wallbox_above_its_minimum_is_lowered_first(self):
        car2 = R(power_w=7360.0, current_a=16, phases=2)
        house = House(Car(), base=6.0)
        orig = house.readings
        house.readings = lambda: {**orig(), "wb2": car2}
        guard = engine.Guard([wb(), D(id="wb2", name="Wallbox 2", kind="wallbox", priority=3)] + others())
        out = drive(guard, house, 1.5)
        self.assertEqual(kinds(out, "wb_pause"), [])
        self.assertTrue([a for _, a in out if a.device_id == "wb2" and a.kind == "set_current"])

    def test_given_back_first_reverse_order(self):
        house = House(Car(), base=lambda t: 10.0 if t < 8 else 1.0, pool=True)
        guard = engine.Guard([wb()] + others())
        out = drive(guard, house, 40)
        resume = kinds(out, "wb_resume")
        pool_on = [(t, a) for t, a in out if a.device_id == "pool" and a.kind == "turn_on"]
        self.assertTrue(resume and pool_on, texts(out))
        self.assertLess(resume[0][0], pool_on[0][0], "the last measure is taken back first")

    def test_precautionary_lock_is_untouched(self):
        """A setting with a start power that is not running: its precautionary lock works as before, the pause comes only when the
        normal levers are used up."""
        house = House(Car(), base=8.0)
        hp = D(id="wp", name="WP", kind="setting", priority=5, power_w=1500, start_kw=5.0)
        guard = engine.Guard([wb(), hp] + others())
        orig = house.readings
        house.readings = lambda: {**orig(), "wp": R(releasable=True, power_w=0.0)}
        out = drive(guard, house, 6)
        self.assertTrue(kinds(out, "wb_pause"), texts(out))


class ObserveTests(unittest.TestCase):
    def test_observe_mode_only_says_it(self):
        house = House(Car())
        guard = engine.Guard([wb()] + others())
        out = drive(guard, house, 20, real=False)
        self.assertEqual(kinds(out, "wb_pause"), [])
        self.assertNotIn("paused", guard.interventions.get("wb", {}))
        notes = [a.text for _, a in out if "würde pausiert" in a.text]
        self.assertTrue(notes, texts(out))
        self.assertLessEqual(len(notes), 2, "once per quarter hour")
        self.assertEqual(house.car.mode, "pv")

    def test_observe_mode_after_the_simulated_lowering(self):
        """In observe mode the readings never change: the simulated lowering to the minimum counts."""
        house = House(Car(current=16), base=10.0)
        out = drive(engine.Guard([wb()] + others()), house, 10, real=False)
        self.assertTrue([a for _, a in out if "würde pausiert" in a.text], texts(out))
        self.assertEqual(kinds(out, "wb_pause"), [])

    def test_observe_only_at_the_device(self):
        house = House(Car())
        guard = engine.Guard([wb(observe_only=True)] + others())
        out = drive(guard, house, 10)
        self.assertEqual(kinds(out, "wb_pause"), [])
        self.assertTrue([a for _, a in out if "würde pausiert" in a.text], texts(out))
        self.assertEqual(house.car.calls, [])


class GiveBackTests(unittest.TestCase):
    def test_not_before_the_minimum_duration(self):
        house = House(Car(), base=lambda t: 8.0 if t < 3 else 1.0)
        guard = engine.Guard([wb(hold_min=10)] + others())
        out = drive(guard, house, 30)
        p, r = kinds(out, "wb_pause"), kinds(out, "wb_resume")
        self.assertTrue(p and r, texts(out))
        self.assertGreaterEqual(r[0][0] - p[0][0], 10 - 1e-9)
        self.assertEqual(r[0][1].value, "pv", "the mode from before")
        self.assertFalse(r[0][1].intervention)
        self.assertIn("wieder erlaubt", r[0][1].text)

    def test_default_minimum_duration_is_five_minutes(self):
        house = House(Car(), base=lambda t: 8.0 if t < 3 else 1.0)
        out = drive(engine.Guard([wb()] + others()), house, 30)
        p, r = kinds(out, "wb_pause"), kinds(out, "wb_resume")
        self.assertTrue(p and r, texts(out))
        self.assertGreaterEqual(r[0][0] - p[0][0], 5 - 1e-9)

    def test_only_with_room_for_the_minimum_current_and_a_margin(self):
        # paused at 6 A x 3 phases = 4.14 kW: room 3.9 kW is not enough (4.14 + margin), 5.5 kW is
        house = House(Car(), base=lambda t: 8.0 if t < 3 else 9.5 - 3.9)
        out = drive(engine.Guard([wb()] + others()), house, 40)
        self.assertTrue(kinds(out, "wb_pause"))
        self.assertEqual(kinds(out, "wb_resume"), [], texts(out))
        house = House(Car(), base=lambda t: 8.0 if t < 3 else 9.5 - 5.5)
        out = drive(engine.Guard([wb()] + others()), house, 40)
        self.assertTrue(kinds(out, "wb_resume"), texts(out))

    def test_no_new_pause_within_the_pause_after_taking_back(self):
        # high, low (resume), high again
        house = House(Car(), base=lambda t: 1.0 if 4 <= t < 14 else 8.0)
        out = drive(engine.Guard([wb(pause_min=20)] + others()), house, 50)
        p, r = kinds(out, "wb_pause"), kinds(out, "wb_resume")
        self.assertTrue(r, texts(out))
        later = [t for t, _ in p if t > r[0][0]]
        self.assertTrue(later, texts(out))
        self.assertGreaterEqual(later[0] - r[0][0], 20 - 1e-9)

    def test_after_the_resume_the_current_is_not_raised_while_the_car_starts(self):
        """The car needs a while to start again: the guard must not give back 16 A (or the full ceiling) in the meantime."""
        house = House(Car(current=16), base=lambda t: 9.0 if t < 10 else 4.0)
        guard = engine.Guard([wb()] + others())
        car = house.car
        orig_apply = car.apply
        started = {}

        def apply(a):   # the car starts again only 2 minutes after it was allowed
            orig_apply(a)
            if a.kind == "wb_resume":
                car.mode = "off"
                started["at"] = True

        car.apply = apply
        out = []
        for i in range(int(40 * 3)):
            t_min = i / 3.0
            if started.get("at") is True:
                started["at"] = t_min + 2.0
            if isinstance(started.get("at"), float) and t_min >= started["at"]:
                car.mode = "pv"
            acts = guard.step(START + timedelta(minutes=t_min), house.grid(t_min), None, house.readings(), LIMIT, MARGIN, True)
            for a in acts:
                out.append((t_min, a))
                house.apply(a)
            if isinstance(started.get("at"), float) and t_min < started["at"]:
                self.assertEqual(car.current, 6, (t_min, texts(out)))
        self.assertTrue(kinds(out, "wb_resume"), texts(out))


class ForcedTests(unittest.TestCase):
    def _paused(self, **kw):
        house = House(Car(**kw))
        guard = engine.Guard([wb(one_phase_option=kw.get("one_phase_option"))] + others())
        drive(guard, house, 4)
        self.assertIn("paused", guard.interventions.get("wb", {}))
        return guard, house

    def test_release_all_allows_again_with_the_old_mode(self):
        guard, house = self._paused()
        acts = guard.release_all(START + timedelta(minutes=5), house.readings(), "Neustart")
        res = [a for a in acts if a.kind == "wb_resume"]
        self.assertEqual([a.value for a in res], ["pv"])
        self.assertNotIn("wb", guard.interventions)

    def test_remembered_over_a_restart(self):
        import json
        guard, house = self._paused()
        saved = json.loads(json.dumps(guard.to_dict()))   # what the store keeps
        new = engine.Guard([wb()] + others())
        new.load(saved)
        acts = new.release_all(START + timedelta(minutes=5), house.readings(), "Neustart")
        self.assertEqual([a.value for a in acts if a.kind == "wb_resume"], ["pv"])

    def test_switch_turned_off_meanwhile_allows_again_at_once(self):
        guard, house = self._paused()
        new = engine.Guard([wb(may_pause=False)] + others())
        new.load(guard.to_dict())
        acts = new.step(START + timedelta(minutes=5), house.grid(5), None, house.readings(), LIMIT, MARGIN, True)
        self.assertEqual([a.value for a in acts if a.kind == "wb_resume"], ["pv"])

    def test_mode_changed_by_someone_stays_theirs(self):
        guard, house = self._paused()
        house.car.mode = "now"   # someone sets "fast" in evcc
        out = drive(guard, house, 30, t0=START + timedelta(minutes=4))
        self.assertEqual(kinds(out, "wb_resume"), [], texts(out))
        self.assertEqual(kinds(out, "wb_pause"), [], "no new pause right away against the user")
        self.assertIn("selbst geändert", texts(out))
        self.assertEqual(house.car.mode, "now")

    def test_not_followed_is_repeated_once_and_reported(self):
        house = House(Car())
        guard = engine.Guard([wb()] + others())
        deaf = house.car.apply
        house.car.apply = lambda a: None if a.kind == "wb_pause" else deaf(a)
        out = drive(guard, house, 6)
        self.assertEqual(len([a for _, a in out if a.kind == "wb_pause"]), 2, texts(out))   # the pause and its repetition
        self.assertTrue(kinds(out, "unconfirmed"), texts(out))

    def _deaf_pause(self, base, pool=True, earlier_current=6):
        """A wallbox that ignores the pause command (review finding 27.11.2026): it goes on charging."""
        house = House(Car(current=earlier_current), base=base, pool=pool)
        guard = engine.Guard([wb()] + others())
        deaf = house.car.apply
        house.car.apply = lambda a: None if a.kind == "wb_pause" else deaf(a)
        return guard, house

    def test_a_pause_that_is_not_followed_is_forgotten(self):
        guard, house = self._deaf_pause(8.0, pool=False)
        out = drive(guard, house, 8)
        self.assertTrue(kinds(out, "unconfirmed"), texts(out))
        self.assertNotIn("wb", guard.interventions, "created only for the pause: removed, nothing stays behind")
        self.assertAlmostEqual(guard._saved_kw(house.readings()), 0.0, places=3)
        self.assertEqual(kinds(out, "wb_resume"), [], "it was never paused: the mode is not touched")
        self.assertEqual(house.car.mode, "pv")

    def test_after_a_failed_pause_an_earlier_lowering_stays(self):
        guard, house = self._deaf_pause(9.0, pool=False, earlier_current=16)
        out = drive(guard, house, 10)
        self.assertTrue(kinds(out, "unconfirmed"), texts(out))
        iv = guard.interventions.get("wb")
        self.assertIsNotNone(iv, "the lowering 16 -> 6 A is still the guard's and is given back later")
        self.assertNotIn("paused", iv)
        self.assertEqual(iv["orig_current"], 16)

    def test_after_a_failed_pause_the_other_devices_are_given_back(self):
        guard, house = self._deaf_pause(lambda t: 8.0 if t < 8 else 1.0)
        out = drive(guard, house, 30)
        self.assertTrue(kinds(out, "unconfirmed"), texts(out))
        self.assertTrue([a for _, a in out if a.device_id == "pool" and a.kind == "turn_on"], texts(out))
        self.assertEqual(kinds(out, "wb_resume"), [])

    def test_no_new_pause_within_the_rest_after_a_failed_pause(self):
        guard, house = self._deaf_pause(8.0, pool=False)
        out = drive(guard, house, 80)
        pauses = [t for t, a in out if a.kind == "wb_pause"]
        miss = [t for t, a in out if a.kind == "unconfirmed"][0]
        later = [t for t in pauses if t > miss]
        self.assertTrue(later, texts(out))
        self.assertGreaterEqual(later[0] - miss, engine.PAUSE_USER_REST_MIN - 1e-9)

    def test_savings_count_the_paused_power(self):
        guard, house = self._paused()
        self.assertAlmostEqual(guard._saved_kw(house.readings()), 6 * 3 * V1 / 1000.0, places=2)


class PhaseTests(unittest.TestCase):
    def _resume_room(self, phases, room):
        house = House(Car(phases=phases), base=lambda t: 9.0 if t < 3 else 9.5 - room)
        guard = engine.Guard([wb()] + others())
        out = drive(guard, house, 40)
        return kinds(out, "wb_pause"), kinds(out, "wb_resume"), out

    def test_one_phase(self):
        p, r, out = self._resume_room(1, 2.2)   # 6 A x 230 V = 1.38 kW + margin
        self.assertTrue(p and r, texts(out))
        p, r, out = self._resume_room(1, 1.6)
        self.assertTrue(p, texts(out))
        self.assertEqual(r, [])

    def test_two_phases(self):
        p, r, out = self._resume_room(2, 3.6)   # 6 A x 2 x 230 V = 2.76 kW + margin
        self.assertTrue(p and r, texts(out))
        p, r, out = self._resume_room(2, 3.0)
        self.assertTrue(p, texts(out))
        self.assertEqual(r, [])

    def test_three_phases(self):
        p, r, out = self._resume_room(3, 3.6)   # 4.14 kW + margin: not enough
        self.assertTrue(p, texts(out))
        self.assertEqual(r, [])
        p, r, out = self._resume_room(3, 5.0)
        self.assertTrue(p and r, texts(out))

    def test_three_phases_with_phase_switching_go_to_one_phase_first(self):
        house = House(Car(phases=3, one_phase_option="1 Phase"), base=9.0)
        guard = engine.Guard([wb(one_phase_option="1 Phase")] + others())
        out = drive(guard, house, 15)
        phase = [t for t, a in out if a.kind == "set_phase"]
        pause = kinds(out, "wb_pause")
        self.assertTrue(phase and pause, texts(out))
        self.assertLess(phase[0], pause[0][0])
        self.assertEqual(guard.interventions["wb"]["paused"]["phases"], 1)


if __name__ == "__main__":
    unittest.main()
