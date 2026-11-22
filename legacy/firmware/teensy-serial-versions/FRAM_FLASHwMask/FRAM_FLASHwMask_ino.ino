#include <SPI.h>

// --- Pin config ---
const int flash_CS_PIN = 0;
uint32_t FLASH_cnt = 0;
uint32_t loop_cnt = 0;
uint32_t mask_FRAM= 0;
uint32_t mask_FLASH = 0;
// --- Flash constants ---
//const uint32_t FLASH_SIZE = 8 * 1024 * 1024; // 8MB
const uint32_t FLASH_SIZE = 8 * 1024 * 512; // 8MB
const uint16_t PAGE_SIZE = 256;
char c = 0;

// --- Commands ---
#define CMD_WRITE_ENABLE 0x06
#define CMD_CHIP_ERASE   0xC7
#define CMD_READ_STATUS  0x05
#define CMD_PAGE_PROGRAM 0x02
#define CMD_READ_DATA    0x03
// -------------------- PIN CONFIG --------------------
const uint8_t CS_PIN   = 10;
const uint8_t HOLD_PIN = 5;
const uint8_t WP_PIN   = 6;

// -------------------- FRAM CONFIG --------------------
const uint16_t FRAM_SIZE = 8192; // 8KB

#define CMD_WREN   0x06
#define CMD_WRITE  0x02
#define CMD_READ   0x03

SPISettings framSPI(100000, MSBFIRST, SPI_MODE0);
// --- SPI settings ---
SPISettings flashSPI(100000, MSBFIRST, SPI_MODE0);

// -------------------- CONTROL --------------------
inline void framEnable() {
  digitalWrite(HOLD_PIN, HIGH); // enable SPI (not paused)
  digitalWrite(WP_PIN, HIGH);   // allow writes
}

inline void framProtect() {
  digitalWrite(WP_PIN, LOW);    // enable write protection
}

// -------------------- LOW LEVEL --------------------
void FRAM_writeEnable() {
  SPI.beginTransaction(framSPI);
  digitalWrite(CS_PIN, LOW);
  SPI.transfer(CMD_WREN);
  digitalWrite(CS_PIN, HIGH);
  SPI.endTransaction();
}

void framWrite(uint16_t addr, const uint8_t *data, uint16_t len) {
  framEnable();
  FRAM_writeEnable();

  SPI.beginTransaction(framSPI);
  digitalWrite(CS_PIN, LOW);

  SPI.transfer(CMD_WRITE);
  SPI.transfer((uint8_t)(addr >> 8));
  SPI.transfer((uint8_t)(addr & 0xFF));

  for (uint16_t i = 0; i < len; i++) {
    SPI.transfer(data[i]);
  }

  digitalWrite(CS_PIN, HIGH);
  SPI.endTransaction();
}

void framRead(uint16_t addr, uint8_t *buf, uint16_t len) {
  framEnable();

  SPI.beginTransaction(framSPI);
  digitalWrite(CS_PIN, LOW);

  SPI.transfer(CMD_READ);
  SPI.transfer((uint8_t)(addr >> 8));
  SPI.transfer((uint8_t)(addr & 0xFF));

  for (uint16_t i = 0; i < len; i++) {
    buf[i] = SPI.transfer(0x00);
  }

  digitalWrite(CS_PIN, HIGH);
  SPI.endTransaction();
}

// -------------------- TEST WRITE --------------------
void writeEntireFRAM() {
  uint8_t buffer[64];
  const uint16_t chunk = sizeof(buffer);
  Serial.println("Writing FRAM Start.");
  for (uint16_t addr = 0; addr < FRAM_SIZE; addr += chunk) {

    for (uint16_t i = 0; i < chunk; i++) {
      buffer[i] = (uint8_t)((addr + i) & 0xFF);
    }

    framWrite(addr, buffer, chunk);
  }

  Serial.println("FRAM write complete.");
}

// -------------------- TEST VERIFY --------------------
void FRAM_Read() {
  uint8_t buf[64];
  const uint16_t chunk = sizeof(buf);
  uint32_t errorCount = 0;
 
 
    
  Serial.println("Starting Read FRAM test...");
    for (uint16_t addr = 0; addr < FRAM_SIZE; addr += chunk) {

      framRead(addr, buf, chunk);

      for (uint16_t i = 0; i < chunk; i++) {
        uint8_t expected = (uint8_t)((addr + i) & 0xFF);

        if (buf[i] != expected) {
          Serial.print("Error @ 0x");
          Serial.print(addr + i, HEX);
          Serial.print(" exp=0x");
          Serial.print(expected, HEX);
          Serial.print(" got=0x");
          Serial.println(buf[i], HEX);
          errorCount++;
        }
      }
    
    loop_cnt++;
    Serial.print(loop_cnt);
    Serial.print(" ...Loop done. Errors: "); 
    Serial.println(errorCount);
  }
}



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

void waitBusy() {
  while (readStatus() & 0x01) {
    delayMicroseconds(50);
  }
}

void chipErase() {
  Serial.println("Chip erase...");
  writeEnable();

  SPI.beginTransaction(flashSPI);
  digitalWrite(flash_CS_PIN, LOW);
  SPI.transfer(CMD_CHIP_ERASE);
  digitalWrite(flash_CS_PIN, HIGH);
  SPI.endTransaction();

  waitBusy();
  Serial.println("Erase done.");
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

  waitBusy();
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

  Serial.println("Programming flash...");

  for (uint32_t addr = 0; addr < FLASH_SIZE; addr += PAGE_SIZE) {

    for (int i = 0; i < PAGE_SIZE; i++) {
      pageBuffer[i] = expectedValue(addr + i);
    }

    pageProgram(addr, pageBuffer, PAGE_SIZE);

    if ((addr % (64 * 1024)) == 0) {
      Serial.printf("Written: %lu KB\n", addr / 1024);
    }
  }

  Serial.println("Programming complete.");
}

// --- FLASH read + upset detection ---
void FLASH_Read() {
  uint8_t readBuf[PAGE_SIZE];
	uint32_t FLASHerrorCount = 0;
  Serial.println("Starting FLASH read...");
	FLASH_cnt++;
  for (uint32_t addr = 0; addr < FLASH_SIZE; addr += PAGE_SIZE) {

    readData(addr, readBuf, PAGE_SIZE);

    for (int i = 0; i < PAGE_SIZE; i++) {
      uint8_t expected = expectedValue(addr + i);

      if (readBuf[i] != expected) {
        Serial.printf("UPSET @ 0x%08lX expected=0x%02X got=0x%02X\n",
                      addr + i, expected, readBuf[i]);
        FLASHerrorCount++;
      }
    }
  }
	Serial.print(FLASH_cnt);
  Serial.print(" ...FLASH Read done. Errors: "); 
  Serial.println(FLASHerrorCount);
  
}

// --- Setup ---
void setup() {
  Serial.begin(115200);
 
  while (!Serial) {}

  pinMode(flash_CS_PIN, OUTPUT);
  digitalWrite(flash_CS_PIN, HIGH);

  SPI.begin();
    Serial.begin(115200);
  delay(1000);

  pinMode(CS_PIN, OUTPUT);
  pinMode(HOLD_PIN, OUTPUT);
  pinMode(WP_PIN, OUTPUT);

  digitalWrite(CS_PIN, HIGH);
  digitalWrite(HOLD_PIN, HIGH); // MUST be HIGH
  digitalWrite(WP_PIN, HIGH);   // MUST be HIGH

  SPI.begin();

  Serial.println("Starting FRAM test...");

  

  Serial.println("Ready.");
  Serial.println("Commands:");
  Serial.println("a = Mask FRAM");
  Serial.println("b = Mask FLASH");
  Serial.println("w = write full flash and FRAM");
  Serial.println("r = start Memory read");
  Serial.println("s = stop and reset all parameters");
}

// --- Loop ---
void loop() {
  if (Serial.available()) {
    c = Serial.read();
  }
  if (c == 'a') { 
  	mask_FRAM = 1;}
  if (c == 'b') { 
  	mask_FLASH = 1;}
  	
  	
  	
  if (c == 'w') {
   if(mask_FRAM == 0){
    	writeEntireFRAM();
    }
  	if(mask_FLASH == 0){
    	writeEntireFlash();
    }

    c = 0;
    }
    
  else if (c == 'r') {
  	if(mask_FRAM == 0){
    	FRAM_Read();
    }
    if(mask_FLASH == 0){
    	FLASH_Read();
    }
  }
  else if (c == 's') {
      
    Serial.println("Stopping Memory read.");
    c = 0;
    mask_FRAM = 0;
    mask_FLASH = 0;
  }
        
    
  
  
}



