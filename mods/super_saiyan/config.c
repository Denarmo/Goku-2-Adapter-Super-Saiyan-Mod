/*
 * Settings: defaults, flash persistence and the companion app's protocol.
 *
 * Flash: the vendor config sector (0x7B000) holds the vendor block at +0x00 and ours
 * at +0x40 ("GKSS", settings, checksum). The vendor erases the whole sector when it
 * saves, so its writer (cntlr_flash_write_config, timer event 3) is replaced by one
 * that writes both blocks.
 *
 * Protocol: HID feature report 2, 63 bytes after the report ID. The app sends a
 * command with SET_REPORT and reads the answer with GET_REPORT:
 *   request  [2][cmd][arg0][arg1][data...]
 *   response [2][cmd][status][payload...]          status 0 = ok, 1 = bad request
 *   0x01 INFO      -> proto, fw version (u16), settings size, output mode,
 *                     controller type, controller connected
 *   0x02 READ      arg0 = offset, arg1 = length (<= 58) -> [offset][length][bytes]
 *   0x03 WRITE     arg0 = offset, arg1 = length, data   (applies immediately)
 *   0x04 SAVE      store the settings in flash (~0.2 s later, in the main loop)
 *   0x05 DEFAULTS  reset the settings (not saved until SAVE)
 *   0x06 LIVE      -> raw cntlr_state_t bytes 0x00..0x3B of the last input frame
 */
#include "ss.h"

#define SS_FLASH      (NS36_CFG_FLASH + 0x40)
#define SS_MAGIC      0x53534B47u               /* "GKSS" */

enum { CMD_INFO = 1, CMD_READ, CMD_WRITE, CMD_SAVE, CMD_DEFAULTS, CMD_LIVE };

ss_settings_t ss;

static const ss_settings_t defaults = {
    .version = SS_SETTINGS_VER, .size = sizeof(ss_settings_t),
    .tm_enable = 1, .tm_speed = 6, .tm_scroll_div = 40,
    .tm_slop = 48, .tm_drag_slop = 160, .tm_hold_ms = 500,
    .remap = { 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19 },
    .turbo_rate = 15,
};

static void copy(void *dst, const void *src, uint32_t n)
{
    uint8_t *d = dst;
    const uint8_t *s = src;
    while (n--) *d++ = *s++;
}

static uint8_t sum8(const uint8_t *p, uint32_t n)
{
    uint8_t c = 0x5A;
    while (n--) c += *p++;
    return c;
}

void ss_defaults(void) { copy(&ss, &defaults, sizeof(ss)); }

/* boot (mod init): flash is memory-mapped */
void ss_load(void)
{
    const uint8_t *f = (const uint8_t *)SS_FLASH;
    if (*(const uint32_t *)f == SS_MAGIC && f[4] == SS_SETTINGS_VER && f[5] == sizeof(ss)
        && f[4 + sizeof(ss)] == sum8(f + 4, sizeof(ss)))
        copy(&ss, f + 4, sizeof(ss));
    else
        ss_defaults();
}

void ss_request_save(void) { rom_timer_start(3, 10, 200); }

/* Replaces cntlr_flash_write_config (0x1000F938): vendor block + ours, one erase. */
static uint8_t vbuf[0x24], sbuf[4 + sizeof(ss_settings_t) + 3];

static __attribute__((noinline)) void fill_buffers(void)
{
    *(uint32_t *)vbuf = 0x46554E32;                 /* "2NUF" */
    copy(vbuf + 4, g_config, 0x1C);
    vbuf[0x20] = cfg_checksum(vbuf, 0x20);
    *(uint32_t *)sbuf = SS_MAGIC;
    copy(sbuf + 4, &ss, sizeof(ss));
    sbuf[4 + sizeof(ss)] = sum8(sbuf + 4, sizeof(ss));
}

void ss_flash_write(void)
{
    fill_buffers();
    rom_flash_guard(1);
    rom_flash_unlock();
    rom_flash_erase_sector(NS36_CFG_SECTOR);
    rom_flash_program(NS36_CFG_SECTOR, vbuf, 0x21);
    rom_flash_program(NS36_CFG_SECTOR + 0x40, sbuf, 5 + sizeof(ss));
    rom_flash_lock();
    rom_flash_guard(0);
}

/* ---- protocol --------------------------------------------------------------- */
static uint8_t resp[64];

uint32_t ss_config_get(uint8_t *out)
{
    copy(out, resp, 64);
    return 64;
}

static void put16(uint8_t *p, int32_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }

static __attribute__((noinline)) void info(uint8_t *r)
{
    volatile cntlr_state_t *st = &NS36_LAST_STATE;
    r[0] = SS_PROTO_VERSION;
    put16(r + 1, SS_FW_VERSION);
    r[3] = sizeof(ss);
    r[4] = (uint8_t)NS36_OUTPUT_MODE;
    r[5] = (uint8_t)st->type;
    r[6] = st->timestamp != 0;
}

/* READ / WRITE a byte range of the settings; returns the status */
static __attribute__((noinline)) uint8_t rw(int write, const uint8_t *in, uint32_t len, uint8_t *r)
{
    uint8_t a0 = in[2], a1 = in[3];
    if (a0 + a1 > sizeof(ss) || a1 > 58) return 1;
    if (write) {
        if (a0 < 2 || a1 > len - 4) return 1;         /* version/size are read-only */
        copy((uint8_t *)&ss + a0, in + 4, a1);
    } else {
        r[0] = a0;
        r[1] = a1;
        copy(r + 2, (uint8_t *)&ss + a0, a1);
    }
    return 0;
}

void ss_config_set(const uint8_t *in, uint32_t len)
{
    uint8_t cmd = in[1], *r = resp + 3;
    for (int i = 0; i < 64; i++) resp[i] = 0;
    resp[0] = 2;
    resp[1] = cmd;
    if (len < 4 || in[0] != 2) { resp[2] = 1; return; }
    switch (cmd) {
    case CMD_INFO:
        info(r);
        break;
    case CMD_READ:
    case CMD_WRITE:
        resp[2] = rw(cmd == CMD_WRITE, in, len, r);
        break;
    case CMD_SAVE:
        ss_request_save();
        break;
    case CMD_DEFAULTS:
        ss_defaults();
        break;
    case CMD_LIVE:   /* raw cntlr_state_t +0x00..+0x3B: type, time, native buttons, sticks,
                        triggers, IMU, touch; the app maps buttons with the firmware's table */
        copy(r, (const void *)0x2000D478, 0x3C);
        break;
    default:
        resp[2] = 1;
    }
}

/* Mod init: runs at boot before the vendor main (RAM only). */
void ss_init(void) { ss_load(); }
