# F30 330e (NBTevo_Y24073J) port notes and tools

This branch adapts BoostDeck, ShiftDeck and Engine Fault Codes to one car: a 2017 F30 330e LCI
plug-in hybrid with head-unit firmware `NBTevo_Y24073J`. It is a car-specific branch, not a
general release. The reference target in `AgentReadMe.md` is unchanged upstream.

## What differs from the reference build

| Area | Reference | This car |
| --- | --- | --- |
| Firmware | `NBTevo_N18032I` | `NBTevo_Y24073J` (ID5 "2403" framework release) |
| Diagnostic gateway | `169.254.21.3` | `169.254.24.115` (compiled into the plugin libraries) |
| SSH | lands on the HMI node | lands on `hu-jacinto`; the HMI is on `hu-omap` (`on -f hu-omap ...`) |
| Plugins folder | exists | `/var/opt/hmi/data/ID5/Plugins` had to be created |

All framework functions the three plugins import exist in this firmware's
`libAppFramework.A.so` and `libCoreFramework.A.so`, and the apps were confirmed working on the car.

## Changes in the source

- Gateway address set to `169.254.24.115` in `plugin.cpp`, `engine_codes.cpp`, `shift_deck.cpp`
  and `mhd_maps.cpp`.
- BoostDeck and ShiftDeck start in metric units.
- BoostDeck's vertical bar shows HV battery charge level instead of MHD+ active ethanol
  (`-DHV_SOC_BAR`, collector option `--hv-soc`). The ethanol path is still built without the flag.
- BoostDeck gains a second page, "Hybrid" (`-DHYBRID_PAGE`), and is displayed as
  "Elina's Dashboard". Both pages are `toolbarHmiState` screens with a left icon toolbar.
- `probe_signals.py` accepts ECU `07` (hybrid battery ECU).

## Signals added for this car

Read-only requests, each matched once against the instrument cluster unless noted.

| Value | ECU | Request | Conversion | Status |
| --- | --- | --- | --- | --- |
| HV charge level | SME `07` | `22 DD BC` | first big-endian word / 10, in % | matched (78 %) |
| Electric range | KOMBI `60` | `22 D1 11` | word 0 / 10, in km | matched (13 km) |
| Total range | KOMBI `60` | `22 D1 11` | word 2 / 10, in km | matched (224 km) |
| HV pack voltage | SME `07` | `22 DD B4` | word / 100, in V | plausible, not cross-checked |
| 12 V system voltage | DME `12` | OBD `01 42` | word / 1000, in V | plausible, not cross-checked |
| Oil temperature | DME `12` | OBD `01 5C` | byte - 40, in C | live value, not cross-checked |
| Fuel level | DME `12` | OBD `01 2F` | byte * 100 / 255, in % | not cross-checked |
| Outside temperature | DME `12` | OBD `01 46` | byte - 40, in C | not cross-checked |

Electric motor torque was not found. ECU address `1A` does not answer on this car.

## Layout findings on this firmware

- `toolbarHmiState` with `toolbarComponents` works for plugin apps (BMW's own ActiveSeating and
  SecurityMenu plugins use it). Toolbar labels come from `tooltipModel`.
- In a toolbar state, component coordinates are relative to the page area to the right of the
  icons. The pages here are 1092 px wide at x = 24.
- The toolbar stays open, and shifts the page right, unless the page has a focusable component.
- The focus frame is drawn on top of everything, so the focus target is a 1 x 1 transparent
  button in the page's bottom-right corner.

## Files here

| File | Purpose |
| --- | --- |
| `build_y24073j.ps1` | Builds the three apps with a Windows-hosted QNX SDP 6.5 (expects `C:\QNX650`), using the same compiler flags as `native/build.sh`. ShiftDeck needs `-fno-strict-aliasing` to match the packaged release. |
| `relabel_bar.py` | Redraws the bar caption in BoostDeck's background image. |
| `make_hybrid_assets.py` | Produced the intermediate layout with a menu screen and the Hybrid page background. |
| `make_toolbar_assets.py` | Produces the final toolbar layout and artwork from that intermediate layout. |
| `scan_dids.py`, `list_ecus.py` | Read-only discovery of which ECUs and identifiers answer. |
| `compare_readback.py` | Compares a tar read back from the head unit with the local app folders. |

The scripts were written for one Windows PC and contain its paths and this car's addresses.
The artwork scripts need Pillow and the Windows font Bahnschrift. They are a record of how the
layout and images were produced. `native/plugin/BoostDeck.xml` is already the final layout, so
the layout steps cannot be re-run on it as it stands.

## Not in this branch

- The image archive. `BoostDeck.xml` here needs images `56301`, `56310`, `56311` and `56312` and
  a redrawn `56300`, which are not in the packaged `dashboard.zip`. Image archives are ignored by
  `source/.gitignore`, as upstream intends.
- Built binaries, the car's framework libraries, VIN, captures and scan results.
- The native host tests were not run for these changes (no host C compiler on the build PC).
