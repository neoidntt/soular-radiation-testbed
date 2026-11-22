// SEU Detector with Flash Memory Scrubbing
// Teensy + Adafruit W25Q16 Flash (SPI)
// Tests actual non-volatile memory corruption
// Updated with CORRECT Adafruit_SPIFlash library API

#include <LiquidCrystal.h>
#include <Adafruit_SPIFlash.h>
#include <SPI.h>

// Initialize LCD: RS=12, E=11, D4=5, D5=4, D6=3, D7=13
LiquidCrystal lcd(12, 11, 5, 4, 3, 13);

// Flash Configuration
// W25Q16 uses standard SPI: MOSI=11, MISO=12, SCK=13, CS=9
#define FLASH_CS 9
Adafruit_SPIFlash flash(FLASH_CS);

// Pin definitions
const int GREEN_LED = 8;    // System OK - no errors
const int YELLOW_LED = 6;   // Scrubbing - fixing errors
const int RED_LED = 7;      // Error detected
const int BUTTON = 2;       // Press to RESET simulation

// Memory configuration
const int MEMORY_SIZE = 8;              // 8 bytes to test (fits in one Flash sector)
const uint32_t FLASH_START_ADDR = 0x0000;  // Start address in Flash

// Data arrays
byte originalData[MEMORY_SIZE] = {0xAA, 0x55, 0xFF, 0x00, 0xF0, 0x0F, 0xCC, 0x33};
byte backupMemory[MEMORY_SIZE];      // Protected backup for comparison
byte readBuffer[MEMORY_SIZE];        // Buffer for reading from Flash

// Statistics
int totalErrors = 0;
int errorsCorrected = 0;
unsigned long lastScrubTime = 0;
const long scrubInterval = 2000;  // Check memory every 2 seconds

bool buttonPressed = false;

void setup() {
  Serial.begin(9600);
  delay(1000);  // Wait for Serial to initialize
  
  // Initialize LCD
  lcd.begin(16, 2);
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("SEU Flash Test");
  lcd.setCursor(0, 1);
  lcd.print("Init...");
  
  // Setup LED and button pins
  pinMode(GREEN_LED, OUTPUT);
  pinMode(YELLOW_LED, OUTPUT);
  pinMode(RED_LED, OUTPUT);
  pinMode(BUTTON, INPUT);
  
  // Initialize SPI
  SPI.begin();
  
  // Initialize Flash
  // API: bool Adafruit_SPIFlash::begin(SPIFlash_Device_t const * device, uint32_t flashClockSpeed)
  if (!flash.begin()) {
    Serial.println("ERROR: Flash chip not found!");
    lcd.clear();
    lcd.print("FLASH ERROR!");
    digitalWrite(RED_LED, HIGH);
    while(1);  // Halt if Flash fails
  }
  
  Serial.println("Flash initialized successfully!");
  
  // Get Flash chip information
  // API: uint32_t getJEDECID()
  Serial.print("Flash JEDEC ID: 0x");
  Serial.println(flash.getJEDECID(), HEX);
  
  // API: uint32_t size()
  Serial.print("Flash Size: ");
  Serial.print(flash.size() / 1024);
  Serial.println(" KB");
  
  // API: uint32_t pageSize()
  Serial.print("Flash Page Size: ");
  Serial.print(flash.pageSize());
  Serial.println(" bytes");
  
  // Initialize Flash with test data
  initializeFlash();
  
  // Turn on green LED - system healthy
  digitalWrite(GREEN_LED, HIGH);
  
  delay(2000);
  lcd.clear();
  
  // Print startup message to Serial Monitor
  Serial.println("=========================================");
  Serial.println(" SEU DETECTOR & FLASH MEMORY SCRUBBING");
  Serial.println(" Cosmic Radiation Simulation");
  Serial.println("=========================================");
  Serial.println();
  Serial.println("Memory Layout:");
  Serial.print("  - Flash Start Address: 0x");
  Serial.println(FLASH_START_ADDR, HEX);
  Serial.print("  - Memory Size: ");
  Serial.print(MEMORY_SIZE);
  Serial.println(" bytes");
  Serial.println();
  Serial.println("Press button to RESET simulation!");
  Serial.println("Auto cosmic rays + scrubbing continue");
  Serial.println();
  
  printMemoryContents();
}

void loop() {
  // Check if button is pressed (TRIGGERS RESET)
  if (digitalRead(BUTTON) == HIGH && !buttonPressed) {
    buttonPressed = true;
    resetSimulation();
    delay(200);
  }
  
  if (digitalRead(BUTTON) == LOW) {
    buttonPressed = false;
  }
  
  // Automatic random cosmic ray hits (2% chance every loop)
  if (random(0, 100) < 2) {
    simulateCosmicRayHit();
    delay(5000);  // Wait 5 seconds before another random hit
  }
  
  // Perform memory scrubbing check every 2 seconds
  if (millis() - lastScrubTime >= scrubInterval) {
    lastScrubTime = millis();
    performMemoryScrubbing();
  }
  
  // Update the LCD display
  updateDisplay();
  
  delay(100);
}

// Initialize Flash with original data
void initializeFlash() {
  Serial.println("Initializing Flash with test data...");
  
  // Erase the sector first (Flash requires erase before write)
  // API: bool eraseSector(uint32_t sectorNumber)
  flash.eraseSector(FLASH_START_ADDR / flash.pageSize());
  delay(100);
  
  // Write original data to Flash
  // API: uint32_t writeBuffer(uint32_t address, const void* data, uint32_t size)
  flash.writeBuffer(FLASH_START_ADDR, originalData, MEMORY_SIZE);
  delay(100);
  
  // Copy to backup memory
  for (int i = 0; i < MEMORY_SIZE; i++) {
    backupMemory[i] = originalData[i];
  }
  
  Serial.println("Flash initialized. Data written:");
  for (int i = 0; i < MEMORY_SIZE; i++) {
    Serial.print("  [");
    Serial.print(i);
    Serial.print("] = 0x");
    Serial.println(originalData[i], HEX);
  }
}

// Simulate a cosmic ray hitting memory (flip one bit)
void simulateCosmicRayHit() {
  Serial.println("\n==========================================");
  Serial.println("       *** COSMIC RAY HIT! ***");
  Serial.println("==========================================");
  
  // Pick a random memory location
  int location = random(0, MEMORY_SIZE);
  
  // Pick a random bit to flip
  int bitToFlip = random(0, 8);
  
  // Read current value from Flash
  // API: uint32_t readBuffer(uint32_t address, void* data, uint32_t size)
  byte original = 0;
  flash.readBuffer(FLASH_START_ADDR + location, &original, 1);
  
  // Flip the bit using XOR
  byte corrupted = original ^ (1 << bitToFlip);
  
  // Read entire sector, modify one byte, erase, and write back
  byte tempBuffer[MEMORY_SIZE];
  flash.readBuffer(FLASH_START_ADDR, tempBuffer, MEMORY_SIZE);
  tempBuffer[location] = corrupted;
  
  // Erase the sector and write corrupted data back to Flash
  flash.eraseSector(FLASH_START_ADDR / flash.pageSize());
  delay(50);
  flash.writeBuffer(FLASH_START_ADDR, tempBuffer, MEMORY_SIZE);
  delay(100);
  
  totalErrors++;
  
  // Print details to Serial Monitor
  Serial.print("-> Memory Location Hit: ");
  Serial.println(location);
  Serial.print("-> Bit Flipped: ");
  Serial.println(bitToFlip);
  Serial.print("-> Data Changed: 0x");
  Serial.print(original, HEX);
  Serial.print(" -> 0x");
  Serial.println(corrupted, HEX);
  Serial.print("-> Total Errors So Far: ");
  Serial.println(totalErrors);
  
  // Visual feedback: Turn on RED LED
  digitalWrite(GREEN_LED, LOW);
  digitalWrite(RED_LED, HIGH);
  
  // Show error on LCD
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("ERROR DETECTED!");
  lcd.setCursor(0, 1);
  lcd.print("Mem[");
  lcd.print(location);
  lcd.print("] bit ");
  lcd.print(bitToFlip);
  
  delay(1500);  // Show error for 1.5 seconds
  
  printMemoryContents();
}

// Memory scrubbing - check and fix errors by comparing with backup
void performMemoryScrubbing() {
  bool errorFound = false;
  
  // Read all memory from Flash
  flash.readBuffer(FLASH_START_ADDR, readBuffer, MEMORY_SIZE);
  
  // Compare with backup
  for (int i = 0; i < MEMORY_SIZE; i++) {
    if (readBuffer[i] != backupMemory[i]) {
      errorFound = true;
      
      Serial.println("\n------------------------------------------");
      Serial.println("     MEMORY SCRUBBING ACTIVE");
      Serial.println("------------------------------------------");
      Serial.print("-> Error Found at Location: ");
      Serial.println(i);
      Serial.print("-> Expected Value: 0x");
      Serial.print(backupMemory[i], HEX);
      Serial.print(" (correct)");
      Serial.println();
      Serial.print("-> Found Value: 0x");
      Serial.print(readBuffer[i], HEX);
      Serial.print(" (corrupted)");
      Serial.println();
      
      // Visual feedback: Turn on YELLOW LED
      digitalWrite(RED_LED, LOW);
      digitalWrite(YELLOW_LED, HIGH);
      
      // Show scrubbing on LCD
      lcd.clear();
      lcd.setCursor(0, 0);
      lcd.print("Scrubbing...");
      lcd.setCursor(0, 1);
      lcd.print("Fixing Mem[");
      lcd.print(i);
      lcd.print("]");
      
      delay(1000);
      
      // FIX THE ERROR - Rebuild buffer with corrected value
      byte tempBuffer[MEMORY_SIZE];
      flash.readBuffer(FLASH_START_ADDR, tempBuffer, MEMORY_SIZE);
      tempBuffer[i] = backupMemory[i];
      
      // Erase and write back
      flash.eraseSector(FLASH_START_ADDR / flash.pageSize());
      delay(50);
      flash.writeBuffer(FLASH_START_ADDR, tempBuffer, MEMORY_SIZE);
      delay(100);
      
      errorsCorrected++;
      
      Serial.println("-> Error CORRECTED! ✓");
      Serial.print("-> Total Corrected: ");
      Serial.println(errorsCorrected);
      Serial.println();
      
      // Verify the fix
      byte verified = 0;
      flash.readBuffer(FLASH_START_ADDR + i, &verified, 1);
      if (verified == backupMemory[i]) {
        Serial.println("-> Verification: SUCCESS!");
      } else {
        Serial.println("-> Verification: FAILED!");
      }
      
      break;  // Fix one error at a time
    }
  }
  
  if (!errorFound) {
    // No errors found - system is healthy
    digitalWrite(YELLOW_LED, LOW);
    digitalWrite(RED_LED, LOW);
    digitalWrite(GREEN_LED, HIGH);
  } else {
    // Error was fixed - show green again
    delay(500);
    digitalWrite(YELLOW_LED, LOW);
    digitalWrite(GREEN_LED, HIGH);
  }
}

// Print current memory contents
void printMemoryContents() {
  Serial.println("\nCurrent Flash Contents:");
  byte tempByte;
  for (int i = 0; i < MEMORY_SIZE; i++) {
    flash.readBuffer(FLASH_START_ADDR + i, &tempByte, 1);
    Serial.print("  [");
    Serial.print(i);
    Serial.print("] = 0x");
    Serial.println(tempByte, HEX);
  }
  Serial.println();
}

// Update LCD display with statistics
void updateDisplay() {
  static unsigned long lastUpdate = 0;
  
  // Update display every 3 seconds when system is healthy
  if (millis() - lastUpdate > 3000 && digitalRead(GREEN_LED) == HIGH) {
    lastUpdate = millis();
    
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("Errors:");
    lcd.print(totalErrors);
    lcd.setCursor(0, 1);
    lcd.print("Fixed:");
    lcd.print(errorsCorrected);
  }
}

// Reset entire simulation to initial state
void resetSimulation() {
  Serial.println("\n=========================================");
  Serial.println("           *** SYSTEM RESET ***");
  Serial.println("=========================================");
  
  // Reset all variables
  totalErrors = 0;
  errorsCorrected = 0;
  lastScrubTime = millis();
  
  // Reinitialize Flash with original data
  initializeFlash();
  
  // Reset LEDs to healthy state
  digitalWrite(GREEN_LED, HIGH);
  digitalWrite(YELLOW_LED, LOW);
  digitalWrite(RED_LED, LOW);
  
  // Reset LCD
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("SEU Detector");
  lcd.setCursor(0, 1);
  lcd.print("Reset Complete");
  delay(1500);
  
  Serial.println("Simulation reset! Ready for new cosmic rays.");
  Serial.println();
}
