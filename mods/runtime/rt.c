/* Minimal freestanding runtime for mods: the compiler may emit calls to these. */
#include <stddef.h>
#include <stdint.h>

void *memcpy(void *d, const void *s, size_t n) {
    uint8_t *dp = d; const uint8_t *sp = s;
    while (n--) *dp++ = *sp++;
    return d;
}
void *memset(void *d, int c, size_t n) {
    uint8_t *dp = d;
    while (n--) *dp++ = (uint8_t)c;
    return d;
}
void __aeabi_memcpy(void *d, const void *s, size_t n) { memcpy(d, s, n); }
void __aeabi_memcpy4(void *d, const void *s, size_t n) { memcpy(d, s, n); }
void __aeabi_memclr(void *d, size_t n) { memset(d, 0, n); }
void __aeabi_memclr4(void *d, size_t n) { memset(d, 0, n); }
void __aeabi_memset(void *d, size_t n, int c) { memset(d, c, n); }
