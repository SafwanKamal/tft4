/*
 * retained.c - retained mode from C: draw the scenery once, save it with
 * FbSaveBg, then each frame erase the sprites (FbRestoreSpr), move them and
 * draw them again. Sprites overlap and pass in front of the scenery without
 * damaging it; LcdPresent sends only what changed.
 * Project: tft4.asm + tft4_config.inc + font6x8.asm + tft4.h + this file.
 */
#include <msp430.h>
#include "tft4.h"

#define N 6

static const Tft4Sprite kBall[] = { 6, 6,
    0x0A, 0xA9, 0x00,  0xAA, 0xA9, 0x90,  0xAA, 0x99, 0x90,
    0xA9, 0x99, 0x80,  0x09, 0x98, 0x00,  0x00, 0x00, 0x00 };

static int16_t bx[N] = { 5, 30, 55, 80, 100, 115 }, by[N] = { 10, 40, 20, 60, 30, 80 };
static int16_t dx[N] = { 1, 2, -1, -2, 3, -1 },     dy[N] = { 2, -1, 1, 2, -2, 3 };

static void drawScenery(void)
{
    int16_t i;
    FbClear(1);                                          /* navy sky */
    for (i = 0; i < 20; i++)                             /* stars */
        FbPixel((i * 37) & 127, (i * 23) % 100, 7);
    FbFillRect(0, 110, TFT4_WH(128, 18), 3);             /* ground */
    FbFillRect(0, 110, TFT4_WH(128, 2), 11);             /* grass */
    FbFillRect(56, 60, TFT4_WH(16, 50), 5);              /* a tower */
    FbText("retained", 40, 116, TFT4_TEXT(7, TFT4_CLEAR));
}

int main(void)
{
    int16_t i;

    WDTCTL = WDTPW | WDTHOLD;
    ClockInit();
    PM5CTL0 &= ~LOCKLPM5;
    TA0EX0 = Tft4ClockMHz / 8 - 1;                       /* 25 Hz frame tick */
    TA0CCR0 = 40000 - 1;
    TA0CTL = TASSEL__SMCLK | ID__8 | MC__UP | TACLR;
    LcdInit();

    drawScenery();
    FbSaveBg();                                          /* the scenery is the background */
    LcdPresentFull();

    for (;;) {
        while (!(TA0CCTL0 & CCIFG)) { }
        TA0CCTL0 &= ~CCIFG;

        for (i = 0; i < N; i++)                          /* 1. erase all ... */
            FbRestoreSpr(kBall, bx[i], by[i]);
        for (i = 0; i < N; i++) {                        /* 2. ... move ... */
            bx[i] += dx[i];
            by[i] += dy[i];
            if (bx[i] < 0 || bx[i] > 122) { dx[i] = -dx[i]; bx[i] += 2 * dx[i]; }
            if (by[i] < 0 || by[i] > 104) { dy[i] = -dy[i]; by[i] += 2 * dy[i]; }
        }
        for (i = 0; i < N; i++)                          /* 3. ... then draw all */
            FbBlit(kBall, bx[i], by[i]);

        LcdPresent();
        LcdWait();
    }
}
