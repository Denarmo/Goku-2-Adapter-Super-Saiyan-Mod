/*
 * USB side, Xbox 360 output mode only.
 *
 * Windows' xusb22 driver binds 045E:028E as a whole and ignores extra interfaces,
 * so the adapter enumerates with its own VID/PID as a composite device and tags
 * interface 0 "XUSB10" with a Microsoft OS 1.0 descriptor: xusb22 still drives the
 * pad (XInput works) and the HID driver gets interface 1, which carries
 *   report 1: a mouse (the touchpad), interrupt IN endpoint 0x82
 *   report 2: a 63-byte vendor feature report, the companion app's config channel
 */
#include "ss.h"

#define MOUSE_EP     0x82
#define USB_VID      0x1209     /* pid.codes */
#define USB_PID      0x0001     /* pid.codes test PID */
#define MS_VENDOR    0x47       /* bRequest for the MS OS feature descriptors */
#define REPORT_CFG   2

static const uint8_t report_desc[] = {
    /* mouse, report 1 */
    0x05, 0x01, 0x09, 0x02, 0xA1, 0x01, 0x85, 0x01, 0x09, 0x01, 0xA1, 0x00,
    0x05, 0x09, 0x19, 0x01, 0x29, 0x03, 0x15, 0x00, 0x25, 0x01,
    0x95, 0x03, 0x75, 0x01, 0x81, 0x02, 0x95, 0x01, 0x75, 0x05, 0x81, 0x03,
    0x05, 0x01, 0x09, 0x30, 0x09, 0x31, 0x09, 0x38, 0x15, 0x81, 0x25, 0x7F,
    0x75, 0x08, 0x95, 0x03, 0x81, 0x06, 0xC0, 0xC0,
    /* vendor config channel, feature report 2 (63 bytes) */
    0x06, 0x00, 0xFF, 0x09, 0x01, 0xA1, 0x01, 0x85, REPORT_CFG, 0x09, 0x02,
    0x15, 0x00, 0x26, 0xFF, 0x00, 0x75, 0x08, 0x95, 0x3F, 0xB1, 0x02, 0xC0,
};

/* Vendor Xbox 360 configuration (interface 0, as the stock firmware serves it) plus
 * interface 1 (HID). */
#define CFG_LEN (49 + 25)
static const uint8_t cfg_desc[CFG_LEN] = {
    0x09, 0x02, CFG_LEN, 0x00, 0x02, 0x01, 0x00, 0x80, 0xFA,
    0x09, 0x04, 0x00, 0x00, 0x02, 0xFF, 0x5D, 0x01, 0x00,
    0x11, 0x21, 0x00, 0x01, 0x01, 0x25, 0x81, 0x14, 0x00, 0x00, 0x00, 0x00, 0x13, 0x01, 0x08, 0x00, 0x00,
    0x07, 0x05, 0x81, 0x03, 0x20, 0x00, 0x01,
    0x07, 0x05, 0x01, 0x03, 0x20, 0x00, 0x01,
    /* interface 1: HID (mouse + config channel) */
    0x09, 0x04, 0x01, 0x00, 0x01, 0x03, 0x00, 0x00, 0x00,
    0x09, 0x21, 0x11, 0x01, 0x00, 0x01, 0x22, sizeof(report_desc), 0x00,
    0x07, 0x05, MOUSE_EP, 0x03, 0x08, 0x00, 0x01,     /* interrupt IN, 8 bytes, 1 ms */
};
/* Stock device descriptor with: bcdUSB 2.00 (Windows only asks 2.0+ devices for MS OS
 * descriptors), class from interfaces (composite), own VID/PID, bcdDevice 1.03. */
static const uint8_t dev_desc[18] = {
    0x12, 0x01, 0x00, 0x02, 0x00, 0x00, 0x00, 0x40,
    USB_VID & 0xFF, USB_VID >> 8, USB_PID & 0xFF, USB_PID >> 8, 0x03, 0x01, 0x01, 0x02, 0x03, 0x01,
};
#define EP_DESC (cfg_desc + CFG_LEN - 7)
#define HID_DESC (cfg_desc + 58)

/* "MSFT100" OS string descriptor (string index 0xEE) */
static const uint8_t ms_os_string[18] = {
    18, 3, 'M', 0, 'S', 0, 'F', 0, 'T', 0, '1', 0, '0', 0, '0', 0, MS_VENDOR, 0,
};
/* Extended compat ID descriptor: interface 0 -> USB\MS_COMP_XUSB10 */
static const uint8_t ms_compat_id[40] = {
    40, 0, 0, 0, 0x00, 0x01, 0x04, 0x00, 1, 0, 0, 0, 0, 0, 0, 0,
    0, 1, 'X', 'U', 'S', 'B', '1', '0', 0, 0,
};

static const uint8_t *const strings[4] = {
    g_x360_str_desc0, g_x360_str_desc1, g_x360_str_desc2, g_x360_str_desc3,
};
static volatile uint8_t ep_ready, ep_busy;

/* Replacement for usb_desc_xbox360 (0x1000DF9C): same answers, plus interface 1. */
const uint8_t *ss_desc_x360(int type, uint32_t index, uint32_t *len)
{
    const uint8_t *p = 0;
    uint32_t n = 0;
    switch (type) {
    case 1: p = dev_desc; n = 18; break;
    case 2: p = cfg_desc; n = sizeof(cfg_desc); break;
    case 3:
        if (index < 4) p = strings[index];
        else if (index == 0xEE) p = ms_os_string;
        if (p) n = p[0];                              /* bLength */
        break;
    case 0x21: p = HID_DESC; n = 9; break;
    case 0x22: p = report_desc; n = sizeof(report_desc); break;
    }
    *len = n;
    return p;
}

/* Wraps usb_set_config (callback table entry 0x1001C224): also open EP 0x82. */
void ss_set_config(void)
{
    usb_set_config();
    if (NS36_OUTPUT_MODE == OUT_XBOX360) {
        rom_usb_ep_enable(g_usb_dev, EP_DESC, 0);
        ep_ready = 1;
        ep_busy = 0;
    }
}

/* Wraps usb_req_vendor (0x1001C218): MS OS extended compat ID. */
int ss_req_vendor(const uint8_t *setup)
{
    if (NS36_OUTPUT_MODE == OUT_XBOX360 && setup[1] == MS_VENDOR && setup[4] == 4) {
        uint32_t n = setup[6] | setup[7] << 8;
        usb_ep0_reply(1, ms_compat_id, n < sizeof(ms_compat_id) ? n : sizeof(ms_compat_id));
        return 0;
    }
    return usb_req_vendor(setup);
}

/* Wraps usb_req_class (0x1001C214): GET/SET_REPORT of the config feature report. */
int ss_req_class(const uint8_t *setup)
{
    if (NS36_OUTPUT_MODE == OUT_XBOX360 && setup[4] == 1 && setup[2] == REPORT_CFG && setup[3] == 3) {
        uint32_t n = setup[6] | setup[7] << 8;
        if (setup[0] == 0xA1 && setup[1] == 0x01) {          /* GET_REPORT */
            uint8_t buf[64];
            uint32_t len = ss_config_get(buf);
            usb_ep0_reply(1, buf, len < n ? len : n);
            return 0;
        }
        if (setup[0] == 0x21 && setup[1] == 0x09) {          /* SET_REPORT: receive data */
            usb_ep0_reply(0, setup, n);                      /* -> ss_ep0_out */
            return 0;
        }
    }
    return usb_req_class(setup);
}

/* Replaces the RAM routine 0x2000C000 that completes EP0 OUT data stages: the
 * original forwards the request to the co-processor in PS4/PS5 modes, then frees. */
void ss_ep0_out(void *xfer)
{
    uint8_t *data = *(uint8_t **)((uint8_t *)xfer + 4), *setup = data - 8;
    uint32_t mode = NS36_OUTPUT_MODE, n = setup[6] | setup[7] << 8;
    if (mode == OUT_PS4 || (mode == OUT_PS5 && *(volatile uint8_t *)0x2000D330))
        msp_forward_request(setup, data, n);
    else if (mode == OUT_XBOX360 && setup[0] == 0x21 && setup[1] == 0x09)
        ss_config_set(data, n);
    rom_free(setup);
}

/* ---- mouse reports -------------------------------------------------------- */
static void tx_done(void *xfer)
{
    void *buf = *(void **)((uint8_t *)xfer + 4);
    if (buf) rom_usb_buf_free(buf);
    ep_busy = 0;
}

int ss_mouse_ready(void) { return ep_ready && !ep_busy; }

int ss_mouse_send(uint8_t btn, int8_t x, int8_t y, int8_t wheel)
{
    uint8_t *buf = rom_usb_buf_alloc(5, 1);
    if (!buf) return 0;
    buf[0] = 1;
    buf[1] = btn;
    buf[2] = (uint8_t)x;
    buf[3] = (uint8_t)y;
    buf[4] = (uint8_t)wheel;
    ep_busy = 1;
    if (usb_ep_send(buf, 5, MOUSE_EP, tx_done))
        return 1;
    ep_busy = 0;
    rom_usb_buf_free(buf);
    return 0;
}
