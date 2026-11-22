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
const uint32_t FLASH_SIZE = 8 * 1024 * 512; // 8MB
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

// -------------------- FMAM LOW LEVEL write enable prior to write address and data--------------------
void FRAM_writeEnable() {
  SPI1.beginTransaction(framSPI);
  digitalWrite(CS_PIN, LOW);
  SPI1.transfer(CMD_WREN);
  digitalWrite(CS_PIN, HIGH);
  SPI1.endTransaction();
}

// -------------------- FRAM TEST WRITE 1 8-bit data--------------------
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

// -------------------- FRAM TEST WRITE --------------------
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

// -------------------- FRAM TEST VERIFY --------------------
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
          Serial.printf("[FRAM] Error @ 0x%04X exp=0x%02X got=0x%02X\n", addr + i, expected, buf[i]);
          errorCount++;
        }
      }
    
    loop_cnt++;
    Serial.print(loop_cnt);
    Serial.print(" ...Loop done. Errors: "); 
    Serial.println(errorCount);
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
      Serial.printf("[FLASH] BUSY >1s at addr 0x%08lX\n", addr);
      warned = true;
    }
    else if ((dt > 1000000) && (dt % 1000000 < 100)) {
      Serial.printf("[FLASH] STILL BUSY t=%lu us addr=0x%08lX\n", dt, addr);
    }
  }
}
void waitBusyErase() {
  uint32_t t0 = micros();

  while (readStatus() & 0x01) {
    delayMicroseconds(100);

    uint32_t dt = micros() - t0;

    if ((dt > 30000000) && (dt % 10000000 < 100)) {
      Serial.printf("[FLASH] ERASE STILL BUSY t=%lu us\n", dt);
    }
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

  waitBusyErase();
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
    Serial.print(" Address: "); 
    Serial.print(readBuf[PAGE_SIZE-1]);
    Serial.print(" ...FLASH Errors: "); 
    Serial.println(FLASHerrorCount);
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
  pinMode(CS_PIN, OUTPUT);
  pinMode(HOLD_PIN, OUTPUT);
  pinMode(WP_PIN, OUTPUT);



  delay(1000);



  digitalWrite(CS_PIN, HIGH);
  digitalWrite(HOLD_PIN, HIGH); // MUST be HIGH
  digitalWrite(WP_PIN, HIGH);   // MUST be HIGH
  SPI.begin();
  SPI1.begin();  

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
  if (start_loop == 1 and c!= 's')
     c = 'r';
  if (c == 'a') { 
  	mask_FRAM = 1;}
  if (c == 'b') { 
  	mask_FLASH = 1;}
  	
  	
  	
  if (c == 'w') {
   uint32_t start_loop = 0;
   if(mask_FRAM == 0){
    	writeEntireFRAM();
    }
  	if(mask_FLASH == 0){
    	writeEntireFlash();
    }

    c = 0;
    }
    
  else if (c == 'r') {
    while (1){
    out_loop_cnt++;
    Serial.print("Start Reading Memmories...loop ");
    delay(1000);
    Serial.println(out_loop_cnt);
  	if(mask_FRAM == 0){
    	FRAM_Read();
    }
    if(mask_FLASH == 0){
    	FLASH_Read();
    }
    Serial.print("Stop Reading ALL Memmories...loop ");
    if(Serial.available()){
    	c = Serial.read();
    }
  if (c == 's') {break;}
    }
  }
  else if (c == 's') {
      
    Serial.println("Stopping Memory read.");
    c = 0;
    mask_FRAM = 0;
    mask_FLASH = 0;
  }
        
    
  
  
}



