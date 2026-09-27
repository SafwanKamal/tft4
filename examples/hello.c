/*
 * hello.c - tft4 from C: text, rectangles, pixels and a sprite, one present.
 * Project: tft4.asm + tft4_config.inc + font6x8.asm + tft4.h + this file,
 * with --code_model=small --data_model=small.
 */
#include <msp430.h>
#include "tft4.h"

/* sprite: width, height, then rows, 2 pixels per byte (0 = transparent) */
static const Tft4Sprite kInvader[] = { 8, 6,
    0x00, 0xBB, 0xBB, 0x00,     /* ..BBBB..   B = green */
    0x0B, 0xBB, 0xBB, 0xB0,     /* .BBBBBB. */
    0xBB, 0x7B, 0xB7, 0xBB,     /* BB7BB7BB   7 = white */
    0xBB, 0xBB, 0xBB, 0xBB,     /* BBBBBBBB */
    0x0B, 0x00, 0x00, 0xB0,     /* .B....B. */
    0xB0, 0x00, 0x00, 0x0B,     /* B......B */
};

int main(void)
{
    int16_t x, i;

    WDTCTL = WDTPW | WDTHOLD;
    ClockInit();
    PM5CTL0 &= ~LOCKLPM5;
    LcdInit();

    FbClear(0);                                          /* black */
    FbFillRect(0, 0, TFT4_WH(128, 12), 1);               /* navy title bar */
    FbText("Hello from C", 28, 2, TFT4_TEXT(10, TFT4_CLEAR));

    /* FbText returns the x after the text: build a line from pieces */
    x = FbText("score ", 4, 24, TFT4_TEXT(7, TFT4_CLEAR));
    FbText("01230", x, 24, TFT4_TEXT(10, 2));            /* yellow on plum */

    for (i = 0; i < 5; i++)                              /* a row of sprites */
        FbBlit(kInvader, 14 + i * 22, 50);

    for (i = 0; i < 128; i += 3)                         /* a dotted line */
        FbPixel(i, 70, 12);

    FbFillRect(-10, 100, TFT4_WH(60, 20), 8);            /* clipped at the left */
    FbFillRect(40, 90, TFT4_WH(48, 30), 14);             /* overlapping */

    LcdPresent();
    LcdWait();
    for (;;)
        __bis_SR_register(LPM4_bits);
}
