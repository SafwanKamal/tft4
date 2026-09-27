/*
 * palette_fade.c - palette effects: the picture is drawn once; fading it to
 * black and back only changes the palette (PaletteLoad) and resends the
 * screen (LcdPresentFull). Nothing is redrawn.
 * Project: tft4.asm + tft4_config.inc + font6x8.asm + tft4.h + this file.
 */
#include <msp430.h>
#include "tft4.h"

static uint16_t scaled(uint16_t c, uint16_t level)       /* RGB565 * level / 16 */
{
    uint16_t r = (c >> 11) & 31, g = (c >> 5) & 63, b = c & 31;
    r = (r * level) >> 4; g = (g * level) >> 4; b = (b * level) >> 4;
    return (uint16_t)((r << 11) | (g << 5) | b);
}

int main(void)
{
    uint16_t pal[16], level = 16, i;
    int16_t step = -1;

    WDTCTL = WDTPW | WDTHOLD;
    ClockInit();
    PM5CTL0 &= ~LOCKLPM5;
    TA0EX0 = Tft4ClockMHz / 8 - 1;                       /* 25 Hz */
    TA0CCR0 = 40000 - 1;
    TA0CTL = TASSEL__SMCLK | ID__8 | MC__UP | TACLR;
    LcdInit();

    for (i = 0; i < 16; i++)                             /* 16 bars, one per color */
        FbFillRect(0, i * 8, TFT4_WH(128, 8), i);
    FbText("fade", 52, 60, TFT4_TEXT(0, TFT4_CLEAR));
    LcdPresentFull();

    for (;;) {
        while (!(TA0CCTL0 & CCIFG)) { }
        TA0CCTL0 &= ~CCIFG;
        level += step;                                   /* 16 .. 0 .. 16 */
        if (level == 0 || level == 16) step = -step;
        for (i = 0; i < 16; i++)
            pal[i] = scaled(DefaultPalette[i], level);
        PaletteLoad(pal);                                /* ~0.35 ms */
        LcdPresentFull();                                /* ~17 ms at 16 MHz */
        LcdWait();
    }
}
