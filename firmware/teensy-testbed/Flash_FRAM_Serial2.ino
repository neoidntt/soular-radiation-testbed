#include <SPI.h>

// ---------------- FLASH ----------------
const int flash_CS_PIN = 10;
const uint32_t FLASH_SIZE = 8 * 1024 * 512;
const uint16_t PAGE_SIZE = 256;

#define CMD_WRITE_ENABLE 0x06
#define CMD_CHIP_ERASE   0xC7
#define CMD_READ_STATUS  0x05
#define CMD_PAGE_PROGRAM 0x02
#define CMD_READ_DATA    0x03

SPISettings flashSPI(1000000, MSBFIRST, SPI_MODE0);

uint32_t FLASH_cnt = 0;
uint32_t Total_FLASHerrorCount = 0;

// ---------------- FRAM ----------------
const uint8_t CS_PIN = 0;
const uint8_t HOLD_PIN = 40;
const uint8_t WP_PIN = 41;

#define CMD_WREN  0x06
#define CMD_WRITE 0x02
#define CMD_READ  0x03

const uint16_t FRAM_SIZE = 8192;
SPISettings framSPI(1000000, MSBFIRST, SPI_MODE0);

uint32_t Total_errorCount = 0;

// ---------------- GLOBAL ----------------
uint32_t start_loop = 0;
uint32_t mask_FRAM = 0;
uint32_t mask_FLASH = 0;
uint32_t out_loop_cnt = 0;
uint32_t loop_cnt = 0;
char c = 0;

// ---------------- STOP ----------------
bool checkForStop() {
  if (Serial2.available()) {
    char x = Serial2.read();
    if (x == 's') {
      start_loop = 0;
      Serial2.println("[STOP]");
      return true;
    }
  }
  return false;
}

// ---------------- FRAM ----------------
void FRAM_writeEnable() {
  SPI1.beginTransaction(framSPI);
  digitalWrite(CS_PIN, LOW);
  SPI1.transfer(CMD_WREN);
  digitalWrite(CS_PIN, HIGH);
  SPI1.endTransaction();
}

void framWrite(uint16_t addr, uint8_t *data, uint16_t len) {
  FRAM_writeEnable();

  SPI1.beginTransaction(framSPI);
  digitalWrite(CS_PIN, LOW);

  SPI1.transfer(CMD_WRITE);
  SPI1.transfer(addr >> 8);
  SPI1.transfer(addr & 0xFF);

  for (int i = 0; i < len; i++) {
    SPI1.transfer(data[i]);
  }

  digitalWrite(CS_PIN, HIGH);
  SPI1.endTransaction();
}

void framRead(uint16_t addr, uint8_t *buf, uint16_t len) {
  SPI1.beginTransaction(framSPI);
  digitalWrite(CS_PIN, LOW);

  SPI1.transfer(CMD_READ);
  SPI1.transfer(addr >> 8);
  SPI1.transfer(addr & 0xFF);

  for (int i = 0; i < len; i++) {
    buf[i] = SPI1.transfer(0);
  }

  digitalWrite(CS_PIN, HIGH);
  SPI1.endTransaction();
}

void writeEntireFRAM() {
  uint8_t buf[64];

  Serial2.println("[FRAM WRITE] START");

  for (uint16_t addr = 0; addr < FRAM_SIZE; addr += 64) {
    if (checkForStop()) return;

    for (int i = 0; i < 64; i++) {
      buf[i] = (addr + i) & 0xFF;
    }

    framWrite(addr, buf, 64);

    if ((addr & 0x1FF) == 0) {
      Serial2.print("[FRAM WRITE] 0x");
      Serial2.println(addr, HEX);
    }
  }

  Serial2.println("[FRAM WRITE] DONE");
}

void FRAM_Read() {
  uint8_t buf[64];
  uint32_t errorCount = 0;

  Serial2.println("[FRAM READ] START");

  for (uint16_t addr = 0; addr < FRAM_SIZE; addr += 64) {
    if (checkForStop()) return;

    framRead(addr, buf, 64);

    for (int i = 0; i < 64; i++) {
      uint8_t expected = (addr + i) & 0xFF;

      if (buf[i] != expected) {
        errorCount++;
        Total_errorCount++;
         
      Serial2.print("[FRAM READ ERROR] 0x");
      Serial2.print(addr+i, HEX);
      Serial2.print(" expected_data=");
      Serial2.print(expected);
      Serial2.print(" Read_Data=");
      Serial2.print(buf[i] );
      Serial2.print(" err=");
      Serial2.print(errorCount);
      Serial2.print(" Total_errorCount=");
      Serial2.println(Total_errorCount);
    
      }
    
    if (((addr +i) & 0xFF) <4) {
      Serial2.print("[FRAM READ STATUS] 0x");
      Serial2.print(addr+i, HEX);
      Serial2.print(" expected_data=");
      Serial2.print(expected);
      Serial2.print(" Read_Data=");
      Serial2.print(buf[i] );
      Serial2.print(" err=");
      Serial2.print(errorCount);
      Serial2.print(" Total_errorCount=");
      Serial2.println(Total_errorCount);
    }}
    if ((addr & 0x3FF) == 0) {
      Serial2.print("[FRAM READ] 0x");
      Serial2.print(addr, HEX);
      Serial2.print(" err=");
      Serial2.println(errorCount);
    }
  }

  Serial2.print("[FRAM READ] DONE err=");
  Serial2.println(errorCount);
}

// ---------------- FLASH ----------------
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
  uint8_t s = SPI.transfer(0);
  digitalWrite(flash_CS_PIN, HIGH);
  SPI.endTransaction();
  return s;
}

bool waitBusy() {
  uint32_t lastPrint = millis();

  while (readStatus() & 0x01) {
    if (checkForStop()) return false;

    if (millis() - lastPrint > 2000) {
      Serial2.println("[FLASH BUSY]");
      lastPrint = millis();
    }

    delayMicroseconds(10);
  }

  return true;
}

bool chipErase() {
  Serial2.println("[FLASH ERASE] START");

  writeEnable();

  SPI.beginTransaction(flashSPI);
  digitalWrite(flash_CS_PIN, LOW);
  SPI.transfer(CMD_CHIP_ERASE);
  digitalWrite(flash_CS_PIN, HIGH);
  SPI.endTransaction();

  if (!waitBusy()) return false;

  Serial2.println("[FLASH ERASE] DONE");
  return true;
}

bool pageProgram(uint32_t addr, uint8_t *data) {
  writeEnable();

  SPI.beginTransaction(flashSPI);
  digitalWrite(flash_CS_PIN, LOW);

  SPI.transfer(CMD_PAGE_PROGRAM);
  SPI.transfer(addr >> 16);
  SPI.transfer(addr >> 8);
  SPI.transfer(addr);

  for (int i = 0; i < PAGE_SIZE; i++) {
    SPI.transfer(data[i]);
  }

  digitalWrite(flash_CS_PIN, HIGH);
  SPI.endTransaction();

  return waitBusy();
}

void readData(uint32_t addr, uint8_t *buf) {
  SPI.beginTransaction(flashSPI);
  digitalWrite(flash_CS_PIN, LOW);

  SPI.transfer(CMD_READ_DATA);
  SPI.transfer(addr >> 16);
  SPI.transfer(addr >> 8);
  SPI.transfer(addr);

  for (int i = 0; i < PAGE_SIZE; i++) {
    buf[i] = SPI.transfer(0);
  }

  digitalWrite(flash_CS_PIN, HIGH);
  SPI.endTransaction();
}

void writeEntireFlash() {
  uint8_t buf[PAGE_SIZE];

  if (!chipErase()) return;

  Serial2.println("[FLASH WRITE] START");

  for (uint32_t addr = 0; addr < FLASH_SIZE; addr += PAGE_SIZE) {
    if (checkForStop()) return;

    for (int i = 0; i < PAGE_SIZE; i++) {
      buf[i] = (addr + i) & 0xFF;
    }

    if (!pageProgram(addr, buf)) return;

    if ((addr & 0xFFFF) == 0) {
      Serial2.print("[FLASH WRITE] 0x");
      Serial2.println(addr, HEX);
    }
  }

  Serial2.println("[FLASH WRITE] DONE");
}

void FLASH_Read() {
  uint8_t buf[PAGE_SIZE];
  uint32_t err = 0;

  Serial2.println("[FLASH READ] START");

  for (uint32_t addr = 0; addr < FLASH_SIZE; addr += PAGE_SIZE) {
    if (checkForStop()) return;

    readData(addr, buf);

    for (int i = 0; i < PAGE_SIZE; i++) {
      uint8_t expected = (addr + i) & 0xFF;
      if (buf[i] != expected) {
        err++;
        Total_FLASHerrorCount++;
        
      Serial2.print("[FLASH READ ERROR] 0x");
      Serial2.print(addr+i, HEX);
      Serial2.print(" err=");
      Serial2.print(err);
      Serial2.print(" expected_data=");
      Serial2.print(expected);
      Serial2.print(" Read_Data=");
      Serial2.print(buf[i] );
      Serial2.print(" Total_err=");
      Serial2.println(Total_FLASHerrorCount);
    }
      
    

    if (((addr +i) & 0x1FFF) <4) {
      Serial2.print("[FLASH READ STATUS] 0x");
      Serial2.print(addr+i, HEX);
      Serial2.print(" err=");
      Serial2.print(err);
      Serial2.print(" expected_data=");
      Serial2.print(expected);
      Serial2.print(" Read_Data=");
      Serial2.print(buf[i] );
      Serial2.print(" Total_err=");
      Serial2.println(Total_FLASHerrorCount);
    }}

    if ((addr & 0xFFFF) == 0) {
      Serial2.print("[FLASH READ] 0x");
      Serial2.print(addr, HEX);
      Serial2.print(" err=");
      Serial2.print(err);
      Serial2.print(" Total_err=");
      Serial2.println(Total_FLASHerrorCount);
    }
  }

  Serial2.print("[FLASH READ] DONE err=");
  Serial2.println(err);
}

// ---------------- SETUP ----------------
void setup() {
  Serial2.begin(115200);

  pinMode(flash_CS_PIN, OUTPUT);
  digitalWrite(flash_CS_PIN, HIGH);

  pinMode(CS_PIN, OUTPUT);
  pinMode(HOLD_PIN, OUTPUT);
  pinMode(WP_PIN, OUTPUT);

  digitalWrite(HOLD_PIN, HIGH);
  digitalWrite(WP_PIN, HIGH);

  SPI.begin();
  SPI1.begin();

  Serial2.println("Ready");
}

// ---------------- LOOP ----------------
void loop() {

  while (Serial2.available()) {
    char in = Serial2.read();
    if (in == '\n' || in == '\r') continue;
    c = in;
    if (c == 's') start_loop = 0;
  }

  if (c == 'a') { mask_FRAM = 1; c = 0; return; }
  if (c == 'b') { mask_FLASH = 1; c = 0; return; }

  if (c == 'w') {
    Serial2.println("[WRITE MODE]");
    if (!mask_FRAM) writeEntireFRAM();
    if (!mask_FLASH) writeEntireFlash();
    c = 0;
    return;
  }

  if (c == 'r') {
    Serial2.println("[READ MODE]");
    start_loop = 1;
    c = 0;
  }

  while (start_loop == 1) {

    if (checkForStop()) break;

    if (!mask_FRAM) FRAM_Read();
    if (start_loop == 0) break;

    if (!mask_FLASH) FLASH_Read();
    if (start_loop == 0) break;

    delay(200);
  }

  c = 0;
}