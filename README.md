# SOULAR: Low-Cost Radiation Testbed for FRAM and Flash SPI Memory

**Experimental Characterization and Comparative Analysis of Radiation-Induced Bit-Flip Errors in FRAM and Flash SPI Embedded Systems via a Teensy 4.1 Testbed**

A student research project from University Gardens High School (Puerto Rico), done under **SOULAR**
(*Students on Using Logic in AeRospace and AI*), a mentoring initiative that connects high school students
with real aerospace and AI work. It was mentored by Melanie Berg (IEEE Member).

[**View the final poster (PDF)**](docs/posters/Soular-poster_Final_101.pdf)

> Final posters are in [`docs/posters/`](docs/posters/).

## The question

Can a low-cost, firmware-based pipeline reliably **detect, log and compare radiation-induced bit-flip errors** in
FRAM and Flash SPI memory in real time? Can it give engineers the numbers they need to pick memory for space-grade
embedded systems? And can cheap hardware keep its signal integrity over the long cable runs and electrically noisy
conditions of a real radiation facility?

## What we built

A modular testbed around a **Teensy 4.1** (Cortex-M7, 600 MHz) that exercises two devices under test (DUTs) over a
shared 4-wire SPI bus:

| | FRAM | Flash |
|---|---|---|
| Part | Fujitsu MB85RS64 | Winbond W25Q16 |
| Size | 8 KB (8,192 B) | 4 MB test region (16,384 pages x 256 B) |
| Chip select | Teensy pin 10 (per poster) | Teensy pin 9 (per poster) |
| Method | Write known pattern, then read and compare each byte | Same |

- The Teensy writes a known pattern, reads everything back in a continuous loop, and counts mismatches.
- Errors stream over UART (`Serial4`, 115200 baud, 3.3 V logic) to a laptop as tagged plaintext lines.
- A Python GUI, the **Memory Test Monitor**, shows live error-rate plots and a serial console, and logs to CSV.
- Signals travel to the DUT over **BNC coaxial cable** so every signal has its own ground return. Jumper wires were
  too noisy at the facility.
- The error classifier labels each mismatch as single-bit, multi-bit or block/catastrophic.

```
PC #1 (Python monitor) <--Serial I/O--> Teensy 4.1 --4-wire SPI--> FRAM (DUT 1)
                                                         \-------> Flash (DUT 2)
PC #2 supplies power
```

## Test environments

| Environment | How we tested | Outcome |
|---|---|---|
| **Proton** | DUT powered and biased in the beam chamber, live monitoring through long BNC cabling. | Data obtained. |
| **Neutron** | Same live approach. Neutrons pass through shielding easily. | Too noisy to get usable data. |
| **TID / gamma (Co-60)** | Passive dose steps at the VPT RAD TID facility. DUT is irradiated, then removed and verified on the full system. | The testbed worked. We looked for the dose step where the DUT stops working. |

See [`docs/notes/SOULAR TESTING SUMMARY.txt`](docs/notes/SOULAR%20TESTING%20SUMMARY.txt) for the raw lab notes.

## Companion math project

[`docs/posters/SOULAR_Math_Posters_0.2.pdf`](docs/posters/SOULAR_Math_Posters_0.2.pdf) is a second poster set. It
covers heavy-ion data statistics and curve fitting using the **Weibull cross-section model**:

```
sigma(LET) = sigma_SAT * (1 - exp(-((LET - LET0) / W)^s))   for LET >= LET0
```

Here LET is linear energy transfer (MeV·cm²/mg), `sigma_SAT` is the saturation cross-section, `LET0` is the onset
threshold, and `W`, `s` are shape parameters. The result is that cross-section rises with LET, so a higher-LET
particle is more likely to cause an upset. LET values came from the Texas A&M Cyclotron Institute heavy-ion beam
list. The fitting code is in [`software/curve-fitting/`](software/curve-fitting/).

## Repository layout

```
firmware/
  teensy-testbed/          Flash_FRAM_Serial2.ino, the final Teensy 4.1 firmware
  early-prototypes/        Earlier SEU-detector / memory-scrubbing sketches (LCD + LEDs)
software/
  memory-test-monitor/     Python Tk GUI: live plots, serial log, CSV export
  curve-fitting/           Weibull fit tool (CLI, desktop GUI, drag-and-drop web app)
  math-graphing/           Early scatter-plot and curve-fit experiments
data/
  pre-radiation-baseline/  Baseline CSV logs (2026-05-01), no interruption
  pre-radiation-interruption/
  Curve-Fitting_TID_DRAFT.xlsx
docs/
  posters/                 Final posters (PDF + PPTX) and drafts
  presentations/           Final presentation and drafts
  notes/                   Meeting notes, testing summary, NASA TID report
  photos/                  Test setup photos (HEIC/JPG)
  SOULAR_Timetables.pdf
hardware/                  CE3 Pro 3D-print G-code for Teensy 4.1 hardware
```

## Quick start

**Firmware.** Install Arduino IDE with [Teensyduino](https://www.pjrc.com/teensy/td_download.html). Open
`firmware/teensy-testbed/Flash_FRAM_Serial2.ino` and upload it to a Teensy 4.1. The early prototypes also need the
[FRAM_MB85RS_SPI](https://github.com/christophepersoz/FRAM_MB85RS_SPI) and
[Adafruit_SPIFlash](https://github.com/adafruit/Adafruit_SPIFlash) libraries, which are not vendored here.

**Monitor GUI.**

```bash
pip install pyserial matplotlib
python software/memory-test-monitor/memory_test_monitor_v3.py
```

Pick the serial port (115200 baud). The GUI parses the firmware's lines for FRAM chunks, Flash pages and full-scan
summaries, and plots error rate per bucket.

**Curve fitting.**

```bash
pip install numpy pandas scipy matplotlib
python software/curve-fitting/Curvefit.py data.csv --plot   # also: --gui, --web
```

## Authors

William Díaz Medero, Yanichel J. Wiscovitch Vega (testbed); Soto, I., Vargas, S., Rodríguez, W., Malaret, I.
(math / TID posters). Mentors: Prof. Juliette M. Moreno Concepción, Dr. Cárorin Castro Rivera,
Prof. Natcha León Lugo, Prof. Cristobal Vega Adorno. Technical mentors: Melanie Berg, Scott Linton.

## References

Full citations are on the posters. Key sources: Berg (NASA NEPP/HEART), Aguiar et al. 2025 (*Chips* 4(1)),
Marinella 2021 (IEEE TNS 68(5)), Holmes-Siedle and Adams (*Handbook of Radiation Effects*), the Fujitsu MB85RS64 and
Winbond W25Q16 datasheets, and PJRC Teensy 4.1 docs.

## Status and license

Research archive. No license has been chosen yet, so all rights are reserved until one is added.
