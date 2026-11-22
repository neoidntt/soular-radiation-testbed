#include <SPI.h>

// --- Pin config ---
// -------------------- FLASH PIN CONFIG --------------------
const int flash_CS_PIN = 10;
uint32_t FLASH_cnt = 0;
uint32_t loop_cnt = 0;
uint32_t mask_FRAM= 0;
uint32_t mask_FLASH = 0;
uint32_t out_loop_cnt = 0;
uint32_t start_loop = 0;
// --- Flash constants ---
//const uint32_t FLASH_SIZE = 8 * 1024 * 1024; // 8MB
const uint32_t FLASH_SIZE = 8 * 1024 * 512; // 4MB
const uint16_t PAGE_SIZE = 256;
char c = 0;

// --- Commands ---
#define CMD_WRITE_ENABLE 0x06
#define CMD_CHIP_ERASE   0xC7
#define CMD_READ_STATUS  0x05
#define CMD_PAGE_PROGRAM 0x02
#define CMD_READ_DATA    0x03
// -------------------- FRAM PIN CONFIG --------------------
const uint8_t CS_PIN   = 0;
const uint8_t HOLD_PIN = 40;
const uint8_t WP_PIN   = 41;

// -------------------- FRAM CONFIG --------------------
const uint16_t FRAM_SIZE = 8192; // 8KB

#define CMD_WREN   0x06
#define CMD_WRITE  0x02
#define CMD_READ   0x03

SPISettings framSPI(100000, MSBFIRST, SPI_MODE0);
// --- SPI settings ---
SPISettings flashSPI(100000, MSBFIRST, SPI_MODE0);

// -------------------- FRAM CONTROL --------------------
inline void framEnable() {
  digitalWrite(HOLD_PIN, HIGH); // enable SPI (not paused)
  digitalWrite(WP_PIN, HIGH);   // allow writes
}

inline void framProtect() {
  digitalWrite(WP_PIN, LOW);    // enable write protection
}

// -------------------- FRAM LOW LEVEL write enable prior to write address and data --------------------
void FRAM_writeEnable() {
  SPI1.beginTransaction(framSPI);
  digitalWrite(CS_PIN, LOW);
  SPI1.transfer(CMD_WREN);
  digitalWrite(CS_PIN, HIGH);
  SPI1.endTransaction();
}

// -------------------- FRAM TEST WRITE 1 8-bit data --------------------
void framWrite(uint16_t addr, const uint8_t *data, uint16_t len) {
  framEnable();
  FRAM_writeEnable();

  SPI1.beginTransaction(framSPI);
  digitalWrite(CS_PIN, LOW);

  SPI1.transfer(CMD_WRITE);
  SPI1.transfer((uint8_t)(addr >> 8));
  SPI1.transfer((uint8_t)(addr & 0xFF));

  for (uint16_t i = 0; i < len; i++) {
    SPI1.transfer(data[i]);
  }

  digitalWrite(CS_PIN, HIGH);
  SPI1.endTransaction();
}

void framRead(uint16_t addr, uint8_t *buf, uint16_t len) {
  framEnable();

  SPI1.beginTransaction(framSPI);
  digitalWrite(CS_PIN, LOW);

  SPI1.transfer(CMD_READ);
  SPI1.transfer((uint8_t)(addr >> 8));
  SPI1.transfer((uint8_t)(addr & 0xFF));

  for (uint16_t i = 0; i < len; i++) {
    buf[i] = SPI1.transfer(0x00);
  }

  digitalWrite(CS_PIN, HIGH);
  SPI1.endTransaction();
}

bool checkForStop() {
  while (Serial2.available()) {
    char incoming = Serial2.read();
    if (incoming == 's') {
      c = 's';
      return true;
    }
  }
  return false;
}

// -------------------- FRAM TEST WRITE --------------------
void writeEntireFRAM() {
  uint8_t buffer[64];
  const uint16_t chunk = sizeof(buffer);
  Serial2.println("Writing FRAM Start.");
  Serial2.flush();
  
  for (uint16_t addr = 0; addr < FRAM_SIZE; addr += chunk) {
    if (checkForStop()) {
      Serial2.println("Stopped FRAM write.");
      Serial2.flush();
      return;
    }
    for (uint16_t i = 0; i < chunk; i++) {
      buffer[i] = (uint8_t)((addr + i) & 0xFF);
    }
    framWrite(addr, buffer, chunk);
  }

  Serial2.println("FRAM write complete.");
  Serial2.flush();
}

// -------------------- FRAM TEST VERIFY --------------------
void FRAM_Read() {
  uint8_t buf[64];
  const uint16_t chunk = sizeof(buf);
  uint32_t errorCount = 0;
 
  Serial2.println("Starting Read FRAM test...");
  Serial2.flush();
  
  for (uint16_t addr = 0; addr < FRAM_SIZE; addr += chunk) {
    if (checkForStop()) {
      Serial2.println("Stopped FRAM read.");
      Serial2.flush();
      return;
    }

    framRead(addr, buf, chunk);

    for (uint16_t i = 0; i < chunk; i++) {
      uint8_t expected = (uint8_t)((addr + i) & 0xFF);

      if (buf[i] != expected) {
        Serial2.printf("[FRAM] Error @ 0x%04X exp=0x%02X got=0x%02X\n", addr + i, expected, buf[i]);
        Serial2.flush();
        errorCount++;
      }
    }
    
    loop_cnt++;
    Serial2.print(loop_cnt);
    Serial2.print(" ...Loop done. Errors: "); 
    Serial2.println(errorCount);
    Serial2.flush();
  }
}

//////////--------------------FLASH -----------------
// --- Helpers ---
void writeEnable() {
  SPI.beginTransaction(flashSPI);
  digitalWrite(flash_CS_PIN, LOW);
  SPI.transfer(CMD_WRITE_ENABLE);
  digitalWrite(flash_CS_PIN, HIGH);
  SPI.endTransaction();
}

uint8_t readStatus() {
  SPI.beginTransaction(flashSPI);
  digitalWrite(flash_CS_PIN, LOW);
  SPI.transfer(CMD_READ_STATUS);
  uint8_t s = SPI.transfer(0x00);
  digitalWrite(flash_CS_PIN, HIGH);
  SPI.endTransaction();
  return s;
}

void waitBusy(uint32_t addr) {
  uint32_t t0 = micros();
  bool warned = false;

  while (readStatus() & 0x01) {
    delayMicroseconds(50);

    uint32_t dt = micros() - t0;

    if (!warned && dt > 1000000) {
      Serial2.printf("[FLASH] BUSY >1s at addr 0x%08lX\n", addr);
      Serial2.flush();
      warned = true;
    }
    else if ((dt > 1000000) && (dt % 1000000 < 100)) {
      Serial2.printf("[FLASH] STILL BUSY t=%lu us addr=0x%08lX\n", dt, addr);
      Serial2.flush();
    }
  }
}

void waitBusyErase() {
  uint32_t t0 = micros();

  while (readStatus() & 0x01) {
    delayMicroseconds(100);

    uint32_t dt = micros() - t0;

    if ((dt > 30000000) && (dt % 10000000 < 100)) {
      Serial2.printf("[FLASH] ERASE STILL BUSY t=%lu us\n", dt);
      Serial2.flush();
    }
  }
}

void chipErase() {
  Serial2.println("Chip erase...");
  Serial2.flush();
  writeEnable();

  SPI.beginTransaction(flashSPI);
  digitalWrite(flash_CS_PIN, LOW);
  SPI.transfer(CMD_CHIP_ERASE);
  digitalWrite(flash_CS_PIN, HIGH);
  SPI.endTransaction();

  waitBusyErase();
  Serial2.println("Erase done.");
  Serial2.flush();
}

void pageProgram(uint32_t addr, uint8_t *data, uint16_t len) {
  writeEnable();

  SPI.beginTransaction(flashSPI);
  digitalWrite(flash_CS_PIN, LOW);

  SPI.transfer(CMD_PAGE_PROGRAM);
  SPI.transfer((addr >> 16) & 0xFF);
  SPI.transfer((addr >> 8) & 0xFF);
  SPI.transfer(addr & 0xFF);

  for (int i = 0; i < len; i++) {
    SPI.transfer(data[i]);
  }

  digitalWrite(flash_CS_PIN, HIGH);
  SPI.endTransaction();

  waitBusy(addr);
}

void readData(uint32_t addr, uint8_t *buf, uint16_t len) {
  SPI.beginTransaction(flashSPI);
  digitalWrite(flash_CS_PIN, LOW);

  SPI.transfer(CMD_READ_DATA);
  SPI.transfer((addr >> 16) & 0xFF);
  SPI.transfer((addr >> 8) & 0xFF);
  SPI.transfer(addr & 0xFF);

  for (int i = 0; i < len; i++) {
    buf[i] = SPI.transfer(0x00);
  }

  digitalWrite(flash_CS_PIN, HIGH);
  SPI.endTransaction();
}

// --- Globals ---
uint8_t pageBuffer[PAGE_SIZE];

// --- Pattern generator ---
inline uint8_t expectedValue(uint32_t addr) {
  return (uint8_t)(addr & 0xFF);
}

// --- Write entire flash ---
void writeEntireFlash() {
  chipErase();

  Serial2.println("Programming flash...");
  Serial2.flush();

  for (uint32_t addr = 0; addr < FLASH_SIZE; addr += PAGE_SIZE) {
    if (checkForStop()) {
      Serial2.println("Stopped FLASH write.");
      Serial2.flush();
      return;
    }

    for (int i = 0; i < PAGE_SIZE; i++) {
      pageBuffer[i] = expectedValue(addr + i);
    }

    pageProgram(addr, pageBuffer, PAGE_SIZE);

    if ((addr % (64 * 1024)) == 0) {
      Serial2.printf("Written: %lu KB\n", addr / 1024);
      Serial2.flush();
    }
  }

  Serial2.println("Programming complete.");
  Serial2.flush();
}

// --- FLASH read + upset detection ---
void FLASH_Read() {
  uint8_t readBuf[PAGE_SIZE];
  uint32_t FLASHerrorCount = 0;
  
  Serial2.println("Starting FLASH read...");
  Serial2.flush();
  
  FLASH_cnt++;
  
  for (uint32_t addr = 0; addr < FLASH_SIZE; addr += PAGE_SIZE) {
    if (checkForStop()) {
      Serial2.println("Stopped FLASH read.");
      Serial2.flush();
      return;
    }

    readData(addr, readBuf, PAGE_SIZE);

    for (int i = 0; i < PAGE_SIZE; i++) {
      uint8_t expected = expectedValue(addr + i);

      if (readBuf[i] != expected) {
        Serial2.printf("UPSET @ 0x%08lX expected=0x%02X got=0x%02X\n",
                      addr + i, expected, readBuf[i]);
        Serial2.flush();
        FLASHerrorCount++;
      }
    }
    
    Serial2.print(" Address: "); 
    Serial2.print(addr);
    Serial2.print(" ...FLASH Errors: "); 
    Serial2.println(FLASHerrorCount);
    Serial2.flush();
  }
  
  Serial2.print(FLASH_cnt);
  Serial2.print(" ...FLASH Read done. Errors: "); 
  Serial2.println(FLASHerrorCount);
  Serial2.flush();
}

// --- Setup ---
void setup() {
  Serial2.begin(115200);
 
  while (!Serial2) {}

  pinMode(flash_CS_PIN, OUTPUT);
  digitalWrite(flash_CS_PIN, HIGH);
  pinMode(CS_PIN, OUTPUT);
  pinMode(HOLD_PIN, OUTPUT);
  pinMode(WP_PIN, OUTPUT);

  delay(1000);

  digitalWrite(CS_PIN, HIGH);
  digitalWrite(HOLD_PIN, HIGH); // MUST be HIGH
  digitalWrite(WP_PIN, HIGH);   // MUST be HIGH
  SPI.begin();
  SPI1.begin();  

  Serial2.println("Ready.");
  Serial2.println("Commands:");
  Serial2.println("a = Mask FRAM");
  Serial2.println("b = Mask FLASH");
  Serial2.println("w = write full flash and FRAM");
  Serial2.println("r = start Memory read");
  Serial2.println("s = stop and reset all parameters");
  Serial2.flush();
}

// --- Loop ---
void loop() {
  if (Serial2.available()) {
    c = Serial2.read();
  }
  
  if (start_loop == 1 && c != 's') {
    c = 'r';
  }
  
  if (c == 'a') { 
    mask_FRAM = 1;
    c = 0;
  } 
  else if (c == 'b') { 
    mask_FLASH = 1;
    c = 0;
  } 
  else if (c == 'w') {
    if (mask_FRAM == 0) {
      writeEntireFRAM();
    }
    if (mask_FLASH == 0) {
      writeEntireFlash();
    }
    Serial2.println("[WRITE_COMPLETE]");
    Serial2.flush();
    c = 0;
  }
  else if (c == 'r') {
    while (1) {
      out_loop_cnt++;
      Serial2.print("Start Reading Memmories...loop ");
      delay(1000);
      Serial2.println(out_loop_cnt);
      Serial2.flush();
      
      if (mask_FRAM == 0) {
        FRAM_Read();
        if (c == 's') {
          break;
        }
      }
      if (mask_FLASH == 0) {
        FLASH_Read();
        if (c == 's') {
          break;
        }
      }
      
      Serial2.print("Stop Reading ALL Memmories...loop ");
      Serial2.println(out_loop_cnt);
      Serial2.flush();
      
      if (Serial2.available()) {
        c = Serial2.read();
      }
      
      if (c == 's') {
        break;
      }
    }
    c = 0;
  }
  else if (c == 's') {
    Serial2.println("Stopping Memory read.");
    Serial2.flush();
    c = 0;
    mask_FRAM = 0;
    mask_FLASH = 0;
  }
}