# Hardcopy

Printed things for the game, and how to print them.

| File | What it is | Made by |
|---|---|---|
| `strips.pdf` | Jack designation strips | `strips.py` |
| `cards.pdf` | Operator's cards | `cards.py` |
| `dial-card-WAverly-7-2004.pdf` | Dial card | `dialcard.py` |
| `stream-deck-help.jpg` | Help placard behind the Stream Deck | drawn by hand |
| `call-the-hotel.jpg` | Placard next to the switchboard, with the number to call | drawn by hand |
| `bench/` | Bench sheets and checklists | |

## Printers

**Brother MFC-9330CDW (colour).** Its driver shrinks the page, so print the PDFs at **105%** to
get true size: the strips' 4 in bar came out 93 mm at "100%".

**Brother HL-5470DW.** Print through the CUPS queue `HL5470DW` (socket 9100, BR-Script3). The
automatic queue and IPP Everywhere fail.

## The Stream Deck help placard

Print `stream-deck-help.jpg` from IrfanView on the colour Brother MFC printer: custom print size,
width 15, maintaining the aspect ratio, portrait. That width is what lines the two arrows up with
the Start and mode keys, so keep it if the image is redrawn at the same layout.

## The call-the-hotel placard

Print `call-the-hotel.jpg` from IrfanView on the colour Brother MFC printer: custom print size,
width 26, maintaining the aspect ratio, landscape.
