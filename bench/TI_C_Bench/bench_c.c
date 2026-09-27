/*******************************************************************************
 * Safwan Kamal
 * SEPTEMBER 2026
 * TI_C_Bench - the tft4 benchmark scenes on TI's C driver (grlib +
 * Crystalfontz128x128_ST7735 + the FR6989 HAL), for comparison with TFT4_Bench.
 *   S1 (P1.1): run the next scene, then show its result on the TFT
 *   S2 (P1.2): run all scenes, then show a summary table on the TFT
 *   Each scene: 1 warm-up frame + 64 timed frames, at most 25 frames/s (the
 *   pacing wait is not timed). The segment LCD shows the scene number and
 *   its average time in ms, e.g. "03 26.6".
 * The scenes are drawn the usual way with this driver: erase the old sprite
 * rectangle with the sky color, then draw the image at its new place. There
 * is no transparency, so sprites get black corners and wipe out stars; the
 * timing is what this program is for.
 ******************************************************************************/
#include <msp430.h>
#include <stdint.h>
#include <stdbool.h>
#include "grlib.h"
#include "Crystalfontz128x128_ST7735.h"
#include "bench_data.h"
#include "bench_clock.h"

#define FRAMES      64          /* timed frames per scene */
#define NUM_PIX     64
#define MAX_SPR     32
#define SKY         1
#define WHITE       7
#define YELLOW      10
#define GREEN       11
#define PEACH       15

Graphics_Context g_sContext;

/* scene state; only one scene runs at a time, so the kinds share the RAM
 * (grlib's image code already takes 1 KB of the 2 KB for its palette buffer) */
static union {
    struct {                                    /* moving sprites */
        uint8_t x[MAX_SPR], y[MAX_SPR], oldX[MAX_SPR], oldY[MAX_SPR];
        int8_t dx[MAX_SPR], dy[MAX_SPR];
    } m;
    struct {                                    /* pixel scene */
        uint8_t x[NUM_PIX], y[NUM_PIX], c[NUM_PIX], oldX[NUM_PIX], oldY[NUM_PIX];
    } p;
} st;
static uint16_t rng, frameNo, param;
static uint32_t hudCounter;
static uint8_t hudDigits[5];
static const Scene *scene;
uint16_t avgHund[SCENE_COUNT], worstHund[SCENE_COUNT];   /* results, 1/100 ms */
uint16_t sceneNo;
volatile uint16_t buttonS1, buttonS2;
static char numBuf[8];

/*------------------------------------------------------------------ drawing */
static void fill(int16_t x, int16_t y, int16_t w, int16_t h, uint8_t c)
{
    Graphics_Rectangle r;
    r.xMin = x; r.yMin = y; r.xMax = x + w - 1; r.yMax = y + h - 1;
    Graphics_setForegroundColor(&g_sContext, kPal[c]);
    Graphics_fillRectangle(&g_sContext, &r);
}

static void pixel(int16_t x, int16_t y, uint8_t c)
{
    Graphics_setForegroundColor(&g_sContext, kPal[c]);
    Graphics_drawPixel(&g_sContext, x, y);
}

static void drawBackground(void)
{
    uint16_t i;
    for (i = 0; i < BG_OPS; i++)
        fill(kBgOps[i][0], kBgOps[i][1], kBgOps[i][2], kBgOps[i][3], (uint8_t)kBgOps[i][4]);
}

static void text(const char *s, int16_t x, int16_t y, uint8_t color)
{
    Graphics_setForegroundColor(&g_sContext, kPal[color]);
    Graphics_setBackgroundColor(&g_sContext, kPal[SKY]);
    Graphics_drawString(&g_sContext, (int8_t *)s, -1, x, y, true);
}

static uint16_t textWidth(const char *s)
{
    uint16_t n = 0;
    while (*s++) n++;
    return n * 6;
}

/*------------------------------------------------------------------ numbers */
static uint16_t rand16(void)            /* xorshift16 (7, 9, 8), as suite.py */
{
    rng ^= rng << 7;
    rng ^= rng >> 9;
    rng ^= rng << 8;
    return rng;
}

static char *fmtHund(uint16_t v)        /* "ddd.dd", leading zeros blank */
{
    numBuf[6] = 0;
    numBuf[5] = '0' + v % 10; v /= 10;
    numBuf[4] = '0' + v % 10; v /= 10;
    numBuf[3] = '.';
    numBuf[2] = '0' + v % 10; v /= 10;
    numBuf[1] = v % 10 ? '0' + v % 10 : ' '; v /= 10;
    numBuf[0] = v ? '0' + v % 10 : ' ';
    if (numBuf[0] != ' ' && numBuf[1] == ' ') numBuf[1] = '0';
    return numBuf;
}

static char *fmtInt(uint16_t v)         /* 0..99 */
{
    char *p = numBuf;
    if (v >= 10) *p++ = '0' + v / 10;
    *p++ = '0' + v % 10;
    *p = 0;
    return numBuf;
}

/*------------------------------------------------------------------ segment LCD */
#define SEGA 0x8000
#define SEGB 0x4000
#define SEGC 0x2000
#define SEGD 0x1000
#define SEGE 0x0800
#define SEGF 0x0400
#define SEGG 0x0200
#define SEGM 0x0100
#define SEGH 0x0080
#define SEGK 0x0020
#define SEGQ 0x0008
#define SEGN 0x0002
#define SEGDP 0x0001
static const uint16_t kSegDigit[12] = {
    SEGA+SEGB+SEGC+SEGD+SEGE+SEGF, SEGB+SEGC, SEGA+SEGB+SEGD+SEGE+SEGG+SEGM,
    SEGA+SEGB+SEGC+SEGD+SEGG+SEGM, SEGB+SEGC+SEGF+SEGG+SEGM, SEGA+SEGC+SEGD+SEGF+SEGG+SEGM,
    SEGA+SEGC+SEGD+SEGE+SEGF+SEGG+SEGM, SEGA+SEGB+SEGC, SEGA+SEGB+SEGC+SEGD+SEGE+SEGF+SEGG+SEGM,
    SEGA+SEGB+SEGC+SEGD+SEGF+SEGG+SEGM, 0, SEGG+SEGM };
#define SEG_SPACE 10
#define SEG_DASH  11
/* per position (0 = rightmost): LCDM register for the low / high byte */
static volatile unsigned char *const kSegLo[6] = { &LCDM9, &LCDM16, &LCDM20, &LCDM5, &LCDM7, &LCDM11 };
static volatile unsigned char *const kSegHi[6] = { &LCDM8, &LCDM15, &LCDM19, &LCDM4, &LCDM6, &LCDM10 };

static void segChar(uint8_t pos, uint8_t ch)
{
    *kSegLo[pos] = (uint8_t)kSegDigit[ch];
    *kSegHi[pos] = (uint8_t)(kSegDigit[ch] >> 8);
}

static void showSeg(uint16_t n, uint16_t hund)  /* hund = 0xFFFF: "----" */
{
    uint8_t pos;
    n++;
    segChar(5, n / 10);
    segChar(4, n % 10);
    if (hund == 0xFFFF) {
        for (pos = 0; pos < 4; pos++) segChar(pos, SEG_DASH);
        return;
    }
    hund = (hund + 5) / 10;                     /* tenths */
    for (pos = 0; pos < 4; pos++) {
        uint8_t d = hund % 10;
        segChar(pos, (pos >= 2 && hund == 0) ? SEG_SPACE : d);
        hund /= 10;
    }
    LCDM16 |= SEGDP;                            /* after position 1 */
}

/*------------------------------------------------------------------ scenes */
static void prepFrame(void)                     /* not timed */
{
    uint16_t i;
    switch (scene->kind) {
    case K_MOVERS:
        for (i = 0; i < scene->count; i++) {
            int16_t x = st.m.x[i], y = st.m.y[i];
            st.m.oldX[i] = x; st.m.oldY[i] = y;
            if (!frameNo) continue;
            x += st.m.dx[i];
            if (x < scene->xmin || x > scene->xmax) {
                st.m.dx[i] = -st.m.dx[i];
                x = x < scene->xmin ? scene->xmin : scene->xmax;
            }
            y += st.m.dy[i];
            if (y < scene->ymin || y > scene->ymax) {
                st.m.dy[i] = -st.m.dy[i];
                y = y < scene->ymin ? scene->ymin : scene->ymax;
            }
            st.m.x[i] = x; st.m.y[i] = y;
        }
        break;
    case K_HUD: {
        uint32_t v;
        hudCounter += 7;
        v = hudCounter % 100000;
        for (i = 5; i-- > 0; v /= 10)
            hudDigits[i] = v % 10;
        break;
    }
    case K_PIXELS:
        for (i = 0; i < NUM_PIX; i++) {
            st.p.oldX[i] = st.p.x[i]; st.p.oldY[i] = st.p.y[i];
            st.p.x[i] = rand16() & 127;
            do { st.p.y[i] = rand16() & 127; } while (st.p.y[i] >= 110);
            st.p.c[i] = 8 + (rand16() & 7);
        }
        break;
    case K_FILL:    param = 2 + frameNo % 12; break;
    case K_STRIPES: param = frameNo & 15; break;
    case K_PALETTE: param = frameNo & 3; break;
    }
}

static void drawFrame(void)                     /* timed */
{
    uint16_t i;
    switch (scene->kind) {
    case K_MOVERS: {
        const Graphics_Image *img = scene->img;
        if (frameNo)
            for (i = 0; i < scene->count; i++)       /* erase with the sky color */
                fill(st.m.oldX[i], st.m.oldY[i], img->xSize, img->ySize, SKY);
        for (i = 0; i < scene->count; i++)
            Graphics_drawImage(&g_sContext, img, st.m.x[i], st.m.y[i]);
        break;
    }
    case K_HUD:
        for (i = 0; i < 5; i++)
            Graphics_drawImage(&g_sContext, kDigits[hudDigits[i]], 90 + 7 * i, 2);
        break;
    case K_PIXELS:
        if (frameNo)
            for (i = 0; i < NUM_PIX; i++) pixel(st.p.oldX[i], st.p.oldY[i], SKY);
        for (i = 0; i < NUM_PIX; i++) pixel(st.p.x[i], st.p.y[i], st.p.c[i]);
        break;
    case K_FILL:
        fill(0, 0, 128, 128, (uint8_t)param);
        break;
    case K_STRIPES:
        for (i = 0; i < 18; i++)
            fill((int16_t)(i * 8) - 16 + (int16_t)param, 0, 8, 128, (i & 1) ? 9 : 12);
        break;
    case K_PALETTE:                                 /* no palette on the panel: */
        kPal[SKY] = kPalAnim[param];                /* redraw what uses the color */
        drawBackground();
        break;
    default:                                        /* idle: nothing to do */
        break;
    }
}

void runScene(uint16_t n)
{
    uint32_t sum = 0;
    uint16_t worst = 0, i;
    scene = &kScenes[n];
    showSeg(n, 0xFFFF);
    drawBackground();
    frameNo = 0;
    rng = 0xACE1;
    hudCounter = 12345;
    for (i = 0; i < scene->count; i++) {
        st.m.x[i] = scene->start[i].x;   st.m.y[i] = scene->start[i].y;
        st.m.dx[i] = scene->start[i].dx; st.m.dy[i] = scene->start[i].dy;
    }
    for (frameNo = 0; frameNo <= FRAMES; frameNo++) {
        uint16_t t0, dt;
        while (!(TA0CCTL0 & CCIFG)) ;              /* at most 25 frames/s */
        TA0CCTL0 &= ~CCIFG;
        prepFrame();
        t0 = TA1R;
        drawFrame();
        dt = TA1R - t0;
        if (frameNo) {
            sum += dt;
            if (dt > worst) worst = dt;
        }
    }
    if (scene->kind == K_PALETTE) {                 /* sky color back */
        kPal[SKY] = SKY_RGB;
        drawBackground();
    }
    avgHund[n] = (uint16_t)((sum / FRAMES + 2) / 5);   /* 2 us ticks -> 1/100 ms */
    worstHund[n] = (worst + 2) / 5;
    showSeg(n, avgHund[n]);
}

/*------------------------------------------------------------------ screens */
static void clearScreen(void)
{
    Graphics_setBackgroundColor(&g_sContext, kPal[SKY]);
    Graphics_clearDisplay(&g_sContext);
}

static void showButtons(void)
{
    text("S1: next scene", 4, 92, GREEN);
    text(kScenes[sceneNo].name, 22, 102, WHITE);
    text("S2: run all scenes", 4, 116, GREEN);
}

void showStart(void)
{
    clearScreen();
    text("TI C benchmark", 22, 20, YELLOW);
    text("Press S1 or S2", 22, 50, WHITE);
    showButtons();
}

static void msLine(const char *label, uint16_t hund, int16_t y)
{
    int16_t x = 4 + textWidth(label);
    text(label, 4, y, WHITE);
    text(fmtHund(hund), x, y, YELLOW);
    text(" ms", x + 36, y, WHITE);
}

void showResult(uint16_t n)
{
    int16_t x;
    clearScreen();
    text("TI C benchmark", 22, 4, YELLOW);
    text("Scene ", 4, 20, WHITE);
    x = 4 + 36;
    text(fmtInt(n + 1), x, 20, WHITE);
    x += textWidth(numBuf);
    text(" of ", x, 20, WHITE);
    x += 24;
    text(fmtInt(SCENE_COUNT), x, 20, WHITE);
    text(kScenes[n].name, 4, 32, PEACH);
    msLine("avg  ", avgHund[n], 48);
    msLine("worst", worstHund[n], 58);
    text(BENCH_MHZ > 8 ? "64 frames, 16 MHz" : "64 frames, 8 MHz", 4, 70, WHITE);
    showButtons();
}

void showSummary(void)
{
    uint16_t i;
    clearScreen();
    text("   scene       avg ms", 1, 1, YELLOW);
    for (i = 0; i < SCENE_COUNT; i++) {
        int16_t y = 11 + 8 * i;
        text(fmtInt(i + 1), i >= 9 ? 1 : 7, y, WHITE);
        text(kScenes[i].name, 19, y, PEACH);
        text(fmtHund(avgHund[i]), 91, y, YELLOW);
    }
}

/*------------------------------------------------------------------ setup */
void benchInit(void)
{
    WDTCTL = WDTPW | WDTHOLD;
#if BENCH_MHZ > 8
    FRCTL0 = FRCTLPW | NWAITS_1;                /* FRAM wait state above 8 MHz */
#endif
    CSCTL0_H = CSKEY_H;                         /* MCLK = SMCLK = DCO = BENCH_MHZ */
    CSCTL3 = DIVA__4 | DIVS__4 | DIVM__4;
#if BENCH_MHZ > 8
    CSCTL1 = DCORSEL | DCOFSEL_4;
#else
    CSCTL1 = DCOFSEL_6;
#endif
    CSCTL2 = SELS__DCOCLK | SELM__DCOCLK;
    __delay_cycles(60);
    CSCTL3 = DIVA__1 | DIVS__1 | DIVM__1;
    CSCTL0_H = 0;

    P1DIR &= ~(BIT1 | BIT2);                    /* S1, S2 with pull-ups */
    P1REN |= BIT1 | BIT2;
    P1OUT |= BIT1 | BIT2;
    P1IES |= BIT1 | BIT2;
    PM5CTL0 &= ~LOCKLPM5;
    P1IFG &= ~(BIT1 | BIT2);
    P1IE |= BIT1 | BIT2;

    LCDCPCTL0 = 0xFFC0;                         /* segment LCD, as Pong */
    LCDCPCTL1 = 0xF03F;
    LCDCPCTL2 = 0x00F0;
    LCDCCTL0 |= LCDPRE__16 | LCD4MUX;
    LCDCMEMCTL |= LCDCLRM;
    LCDCCTL0 |= LCDON;

    TA0CCR0 = 40000;                            /* 25 Hz pacing (1 MHz) */
    TA0EX0 = BENCH_MHZ / 8 - 1;
    TA0CTL = TASSEL__SMCLK | ID__8 | MC__UP | TACLR;
    TA1EX0 = BENCH_MHZ / 4 - 1;                 /* 2 us timing ticks */
    TA1CTL = TASSEL__SMCLK | ID__8 | MC__CONTINUOUS | TACLR;

    Crystalfontz128x128_Init();
    Crystalfontz128x128_SetOrientation(LCD_ORIENTATION_UP);
    Graphics_initContext(&g_sContext, &g_sCrystalfontz128x128);
    Graphics_setFont(&g_sContext, &g_sFontFixed6x8);
    sceneNo = 0;
    buttonS1 = buttonS2 = 0;
}

int main(void)
{
    benchInit();
    showStart();
    __enable_interrupt();
    for (;;) {
        if (buttonS1) {
            uint16_t n = sceneNo;
            runScene(n);
            if (++sceneNo >= SCENE_COUNT) sceneNo = 0;
            showResult(n);
        } else if (buttonS2) {
            uint16_t n;
            for (n = 0; n < SCENE_COUNT; n++) runScene(n);
            sceneNo = 0;
            showSummary();
        } else {
            continue;
        }
        buttonS1 = buttonS2 = 0;                /* presses during a run don't count */
    }
}

#ifndef __clang__                               /* (the emulator test builds with clang) */
#pragma vector = PORT1_VECTOR
__interrupt void port1Isr(void)
{
    switch (P1IV) {
    case P1IV_P1IFG1: buttonS1 = 1; break;
    case P1IV_P1IFG2: buttonS2 = 1; break;
    default: break;
    }
}
#endif
