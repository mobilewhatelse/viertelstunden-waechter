# Installation test (fresh Home Assistant in Docker)

Starts a **fresh** Home Assistant container, installs the integration from this repository, sets it up through the
normal dialogs and drives a simulated house (car, pool pump, house load) through observe, active, release and a restart.
It touches nothing outside the container.

## What it checks

- the integration is offered in the config flow, a second entry is refused, devices (wallbox, switchable device, vehicle)
  can be added as subentries, all entities appear, defaults of the switches match the documentation
- observe mode switches nothing; active mode lowers the wallbox (never below the minimum, never stops it), logs the
  reason and gives everything back when the load ends
- the services `create_dashboard`, `send_week_report` and `import_history`
- a restart keeps mode and switches, releases running interventions, leaves *Also carry out the charge plan* off
- no errors of the integration in the log

## Run

```powershell
docker pull ghcr.io/home-assistant/home-assistant:stable
$cfg = "$PWD\tests\install\run"          # working copy of the config, created by you
New-Item -ItemType Directory -Force "$cfg\custom_components" | Out-Null
Copy-Item tests\install\config\configuration.yaml $cfg
Copy-Item custom_components\viertelstunden_waechter "$cfg\custom_components\" -Recurse
docker run -d --name vw-test -p 18123:8123 -v "${cfg}:/config" -e TZ=Europe/Vienna ghcr.io/home-assistant/home-assistant:stable
python tests\install\itest.py          # takes about 15 minutes (it waits for real quarter hours)
docker rm -f vw-test
```

The test runs in real time because the guard works on real quarter hours: an intervention starts when a quarter hour
begins with a high load. A late quarter hour with little energy used so far has plenty of budget left, so *observe*
mode may report "observing" instead of "would intervene" - that is correct behaviour, not a failure.

## hassfest

```powershell
docker pull ghcr.io/home-assistant/hassfest:latest
docker run --rm -v "${PWD}:/github/workspace" ghcr.io/home-assistant/hassfest:latest
```

The `hacs/action` validation needs a public repository, so it can only run once the repository is published.
