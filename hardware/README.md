# PSoC 6 + BGT60TR13C Radar — Archived

This directory holds the radar work that was cut from VisionAssist partway through the project. **None of it runs in the shipped system.** It is preserved because the reasons it failed are more interesting than the code itself.

## What this was supposed to be

An Infineon BGT60TR13C 60 GHz FMCW radar on a PSoC 6 AI Kit, streaming distance measurements over USB serial to the Raspberry Pi. The camera would identify objects, the radar would say how far away they were, and the two would combine into an alert.

## Files

| File | What it is |
|---|---|
| `main.c` | PSoC 6 firmware. Configures the radar, runs range-FFT processing, emits `Distance: X.XX CMS` over UART at 115200 baud. |
| `radar_settings.h` | Chirp configuration — bandwidth, sample count, frame rate. |
| `radar_settings_32samples.h.bak` | Earlier configuration, kept for comparison. |
| `radar.py` | Pi-side host code. Opens the serial port, parses distance frames, applies smoothing and a floor-reflection cutoff. |

The firmware did work. End-to-end tests tracked an approaching object from 6.74 ft down to 0.55 ft while YOLO concurrently reported chair at 90% and person at 96% confidence. This was not abandoned because it wouldn't turn on.

## Why it was cut

**The architectural reason, which is the real one.** Radar returns the range to the nearest reflective surface in its beam. It has no concept of object identity. YOLO returns object identity with no reliable depth. Combining them requires answering a question neither sensor can answer alone: *is the surface the radar is ranging the same object the camera has boxed?*

With one radar antenna and one camera, you cannot. The radar's return is a single scalar for a wide beam. If the camera sees a chair at the left of the frame and a person at the right, and the radar says 180 cm, that number belongs to one of them, or to a wall behind both, and nothing in the data says which. Proper fusion needs 3D spatial localisation — angle-of-arrival from a multi-antenna array, projected into the camera's coordinate frame with a calibrated extrinsic transform. That is a substantially larger project than the one we had time for.

Monocular distance estimation is less accurate than radar. But it is *per-object* by construction: every bounding box gets its own number, correctly associated with the thing it describes. For an assistive device, knowing which object a distance belongs to turned out to matter more than the precision of the distance.

**The practical problems, which made the decision easy:**

- **TX-RX antenna leakage.** Direct coupling between transmit and receive antennas put a large DC component in every frame, corrupting the low-frequency end of the range FFT — precisely the bins that correspond to close targets.
- **Range ceiling around 175 cm.** Under our chirp configuration, reliable returns stopped well short of useful walking-alert distance. VisionAssist warns at 6 to 9 ft, or 180 to 275 cm, which starts right where the radar stopped.
- **No object classification.** A wall, a chair, and a person at the same distance are the same reading.
- **Toolchain friction.** Infineon's ModusToolbox radar tooling did not play well with Apple Silicon, which slowed every firmware iteration.
- **Unstable serial integration.** The USB serial link to the Pi dropped frames under sustained load.

## What was kept

The PSoC board remained physically mounted on the device through the final demo. Its BMI270 IMU is the most likely path to fixing the largest remaining weakness in the vision-only approach: head tilt perturbing distance estimates. That work is on the roadmap, not in this repo.

## Building the firmware

Infineon ModusToolbox, targeting CY8CKIT-062S2-AI. `radar_settings.h` holds the chirp parameters; changing sample count or bandwidth changes the range resolution and the maximum unambiguous range, so read the BGT60TR13C application notes before touching it.
