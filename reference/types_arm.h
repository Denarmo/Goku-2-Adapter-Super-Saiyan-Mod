/* Recovered data types for the ARM main firmware, parsed by Ghidra
 * (tools/ghidra/ExportAll.java) and applied via prototypes_arm.csv and
 * globals_arm.csv. Keep this plain C (no enums with expressions, no asserts).
 * The mod SDK (mods/include/ns36.h) mirrors these definitions. */

typedef unsigned char  uint8_t;
typedef signed short   int16_t;
typedef unsigned short uint16_t;
typedef unsigned int   uint32_t;

/* Normalized controller state, 0x54 bytes. */
typedef struct cntlr_state {
    uint32_t type;          /* 0x00 controller type index 0..7 */
    uint32_t timestamp;     /* 0x04 */
    uint32_t buttons;       /* 0x08 Nintendo-layout bitmap */
    int16_t  lx;            /* 0x0C */
    int16_t  ly;            /* 0x0E */
    int16_t  rx;            /* 0x10 */
    int16_t  ry;            /* 0x12 */
    uint16_t zl;            /* 0x14 */
    uint16_t zr;            /* 0x16 */
    int16_t  accel[3];      /* 0x18 */
    int16_t  gyro[3];       /* 0x1E */
    uint8_t  no_hotkeys;    /* 0x24 nonzero: skip settings hotkeys */
    uint8_t  _unk25[3];
    uint8_t  _unk28[0x1C];
    uint32_t battery;       /* 0x44 */
    uint8_t  _unk48[0x0C];
} cntlr_state_t;

/* Persistent user configuration block at 0x2000d5b8. */
typedef struct cntlr_config {
    uint8_t  turbo[6];      /* 0x00 A,B,X,Y,R1,R2: 0 off, 1, 2 */
    uint8_t  rumble_sens;   /* 0x06 */
    uint8_t  joys_sens_l;   /* 0x07 */
    uint8_t  joys_sens_r;   /* 0x08 */
    uint8_t  l2_sens;       /* 0x09 */
    uint8_t  r2_sens;       /* 0x0A */
    uint8_t  mode_mask;     /* 0x0B */
    uint32_t study[4];      /* 0x0C learned remaps o1..o4 */
} cntlr_config_t;
