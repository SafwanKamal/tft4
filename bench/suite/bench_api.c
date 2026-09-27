/* bench_api.c - thin, data-driven entry points into TI's C driver so the
 * Python benchmark suite can run exactly the same scenes on it as on tft4. */
#include "grlib.h"
#include "Crystalfontz128x128_ST7735.h"

Graphics_Context g_sContext;
const uint32_t kPal[16] = { 0x000000, 0x1D2B53, 0x7E2553, 0x008751, 0xAB5236, 0x5F574F, 0xC2C3C7, 0xFFF1E8,
                            0xFF004D, 0xFFA300, 0xFFEC27, 0x00E436, 0x29ADFF, 0x83769C, 0xFF77A8, 0xFFCCAA };

void __delay_cycles(unsigned long n) { (void)n; }

void c_init(void)
{
    Crystalfontz128x128_Init();
    Crystalfontz128x128_SetOrientation(LCD_ORIENTATION_UP);
    Graphics_initContext(&g_sContext, &g_sCrystalfontz128x128);
    Graphics_setFont(&g_sContext, &g_sFontFixed6x8);
}

void c_fill(int16_t x, int16_t y, int16_t wh, uint16_t color)
{
    Graphics_Rectangle r;
    r.xMin = x; r.yMin = y;
    r.xMax = x + (wh & 0xFF) - 1; r.yMax = y + ((wh >> 8) & 0xFF) - 1;
    Graphics_setForegroundColor(&g_sContext, kPal[color & 15]);
    Graphics_fillRectangle(&g_sContext, &r);
}

void c_image(const Graphics_Image *img, int16_t x, int16_t y)
{
    Graphics_drawImage(&g_sContext, img, x, y);
}

void c_pixel(int16_t x, int16_t y, uint16_t color)
{
    Graphics_setForegroundColor(&g_sContext, kPal[color & 15]);
    Graphics_drawPixel(&g_sContext, x, y);
}
