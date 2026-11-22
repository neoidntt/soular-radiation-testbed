// SEU Detector with Memory Scrubbing
// Simulates cosmic radiation effects on satellite electronics

#include <LiquidCrystal.h>

// Initialize LCD: RS=12, E=11, D4=5, D5=4, D6=3, D7=13
LiquidCrystal lcd(12, 11, 5, 4, 3, 13);

// Pin definitions
const int GREEN_LED = 8;   // System OK - no errors
const int YELLOW_LED = 9;  // Scrubbing - fixing errors
const int RED_LED = 10;    // Error detected
const int BUTTON = 2;      // Press to simulate cosmic ray

// Simulated satellite memory (8 bytes)
const int MEMORY_SIZE = 8;
byte originalData[MEMORY_SIZE] = {0xAA, 0x55, 0xFF, 0x00, 0xF0, 0x0F, 0xCC, 0x33};
byte workingMemory[MEMORY_SIZE];   // Memory that can get corrupted
byte backupMemory[MEMORY_SIZE];    // Protected backup for comparison

// Statistics
int totalErrors = 0;
int errorsCorrected = 0;
unsigned long lastScrubTime = 0;
const long scrubInterval = 2000;  // Check memory every 2 seconds

bool buttonPressed = false;

void setup() {
  Serial.begin(9600);
  
  // Initialize LCD
  lcd.begin(16, 2);
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("SEU Detector");
  lcd.setCursor(0, 1);
  lcd.print("Initializing...");
  
  // Setup LED and button pins
  pinMode(GREEN_LED, OUTPUT);
  pinMode(YELLOW_LED, OUTPUT);
  pinMode(RED_LED, OUTPUT);
  pinMode(BUTTON, INPUT);
  
  // Copy original data to working and backup memory
  for (int i = 0; i < MEMORY_SIZE; i++) {
    workingMemory[i] = originalData[i];
    backupMemory[i] = originalData[i];
  }
  
  // Turn on green LED - system healthy
  digitalWrite(GREEN_LED, HIGH);
  
  delay(2000);
  lcd.clear();
  
  // Print startup message to Serial Monitor
  Serial.println("=========================================");
  Serial.println(" SEU DETECTOR & MEMORY SCRUBBING");
  Serial.println(" Cosmic Radiation Simulation");
  Serial.println("=========================================");
  Serial.println();
  Serial.println("Press button to simulate cosmic ray!");
  Serial.println("System will auto-correct errors every 2 seconds");
  Serial.println();
}

void loop() {
  // Check if button is pressed
  if (digitalRead(BUTTON) == HIGH && !buttonPressed) {
    buttonPressed = true;
    simulateCosmicRayHit();
    delay(200);  // Small delay to prevent multiple triggers
  }
  
  if (digitalRead(BUTTON) == LOW) {
    buttonPressed = false;
  }
  
  // Automatic random cosmic ray hits (rare, like in space)
  // 2% chance every loop (happens randomly every few seconds)
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

// Function: Simulate a cosmic ray hitting memory
void simulateCosmicRayHit() {
  Serial.println("\n==========================================");
  Serial.println("       *** COSMIC RAY HIT! ***");
  Serial.println("==========================================");
  
  // Pick a random memory location (0 to 7)
  int location = random(0, MEMORY_SIZE);
  
  // Pick a random bit to flip (0 to 7)
  int bitToFlip = random(0, 8);
  
  // Save the original value before corruption
  byte original = workingMemory[location];
  
  // FLIP THE BIT - This simulates radiation damage!
  // XOR operation flips one specific bit
  workingMemory[location] ^= (1 << bitToFlip);
  
  totalErrors++;
  
  // Print details to Serial Monitor
  Serial.print("-> Memory Location Hit: ");
  Serial.println(location);
  Serial.print("-> Bit Flipped: ");
  Serial.println(bitToFlip);
  Serial.print("-> Data Changed: 0x");
  Serial.print(original, HEX);
  Serial.print(" -> 0x");
  Serial.println(workingMemory[location], HEX);
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
}

// Function: Memory scrubbing - check and fix errors
void performMemoryScrubbing() {
  bool errorFound = false;
  
  // Check each memory location
  for (int i = 0; i < MEMORY_SIZE; i++) {
    // Compare working memory with backup
    if (workingMemory[i] != backupMemory[i]) {
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
      Serial.print(workingMemory[i], HEX);
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
      
      delay(1000);  // Show scrubbing process
      
      // FIX THE ERROR - Copy correct value from backup
      workingMemory[i] = backupMemory[i];
      errorsCorrected++;
      
      Serial.println("-> Error CORRECTED! ✓");
      Serial.print("-> Total Corrected: ");
      Serial.println(errorsCorrected);
      Serial.println();
      
      break;  // Fix one error at a time (realistic behavior)
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

// Function: Update LCD display with statistics
void updateDisplay() {
  static unsigned long lastUpdate = 0;
  
  // Update display every 3 seconds when system is healthy
  if (millis() - lastUpdate > 3000 && digitalRead(GREEN_LED) == HIGH) {
    lastUpdate = millis();
    
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("Total Errors:");
    lcd.print(totalErrors);
    lcd.setCursor(0, 1);
    lcd.print("Fixed: ");
    lcd.print(errorsCorrected);
  }
}