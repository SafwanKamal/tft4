/* Minimal MSP430 EABI helpers clang expects (TI's compiler would use the
 * hardware multiplier instead; calls are counted so their cost is visible). */
#include <stdint.h>
#include <stddef.h>
volatile uint16_t g_rtCalls;
int16_t __mspabi_mpyi(int16_t a, int16_t b)
{
    uint16_t x = (uint16_t)a, y = (uint16_t)b, r = 0;
    g_rtCalls++;
    while (y) { if (y & 1) r += x; x <<= 1; y >>= 1; }
    return (int16_t)r;
}
int32_t __mspabi_mpyl(int32_t a, int32_t b)
{
    uint32_t x = (uint32_t)a, y = (uint32_t)b, r = 0;
    g_rtCalls++;
    while (y) { if (y & 1) r += x; x <<= 1; y >>= 1; }
    return (int32_t)r;
}
uint32_t __mspabi_divul(uint32_t n, uint32_t d)
{
    uint32_t q = 0, r = 0;
    uint8_t i;
    g_rtCalls++;
    for (i = 0; i < 32; i++) {
        r = (r << 1) | ((n & 0x80000000UL) ? 1 : 0);
        n <<= 1;
        q <<= 1;
        if (r >= d) { r -= d; q |= 1; }
    }
    return q;
}
int32_t __mspabi_divli(int32_t n, int32_t d)
{
    uint8_t neg = 0;
    uint32_t q;
    if (n < 0) { n = -n; neg ^= 1; }
    if (d < 0) { d = -d; neg ^= 1; }
    q = __mspabi_divul((uint32_t)n, (uint32_t)d);
    return neg ? -(int32_t)q : (int32_t)q;
}
void *memcpy(void *d, const void *s, size_t n)
{
    uint8_t *a = d; const uint8_t *b = s;
    while (n--) *a++ = *b++;
    return d;
}
