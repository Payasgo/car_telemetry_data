/*
  ESP32 + MPU6050 + UART GPS -> Wi-Fi UDP -> laptop.
  Arduino libraries: Adafruit MPU6050, Adafruit Unified Sensor,
  TinyGPSPlus, ArduinoJson.
  Independent sensors only; no vehicle CAN/ECU connection.
*/
#include <WiFi.h>
#include <WiFiUdp.h>
#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <TinyGPSPlus.h>
#include <ArduinoJson.h>

// EDIT THESE SETTINGS
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
IPAddress LAPTOP_IP(192, 168, 1, 20); // replace with laptop LAN IPv4
const uint16_t LAPTOP_UDP_PORT = 5005;

static const int I2C_SDA_PIN = 21;
static const int I2C_SCL_PIN = 22;
static const int GPS_RX_PIN = 16; // ESP32 RX <- GPS TX
static const int GPS_TX_PIN = 17; // optional ESP32 TX -> GPS RX
static const uint32_t GPS_BAUD = 9600;
static const uint32_t SEND_INTERVAL_MS = 100; // target 10 Hz

Adafruit_MPU6050 mpu;
TinyGPSPlus gps;
HardwareSerial GPSSerial(2);
WiFiUDP udp;
uint32_t lastSendMs = 0;
uint32_t packetCounter = 0;
bool imuReady = false;

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("ESP32 IP: ");
  Serial.println(WiFi.localIP());
  udp.begin(5006);
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  imuReady = mpu.begin(); // default address 0x68
  if (imuReady) {
    mpu.setAccelerometerRange(MPU6050_RANGE_4_G);
    mpu.setGyroRange(MPU6050_RANGE_500_DEG);
    mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
    Serial.println("MPU6050 ready.");
  } else {
    Serial.println("ERROR: MPU6050 not detected; check wiring/address.");
  }
  GPSSerial.begin(GPS_BAUD, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);
  connectWiFi();
}

void loop() {
  while (GPSSerial.available()) gps.encode(GPSSerial.read());
  if (WiFi.status() != WL_CONNECTED) connectWiFi();

  uint32_t now = millis();
  if (now - lastSendMs < SEND_INTERVAL_MS) {
    delay(2);
    return;
  }
  lastSendMs = now;

  float ax=NAN, ay=NAN, az=NAN, gx=NAN, gy=NAN, gz=NAN, tempC=NAN;
  if (imuReady) {
    sensors_event_t accel, gyro, temp;
    mpu.getEvent(&accel, &gyro, &temp);
    ax=accel.acceleration.x; ay=accel.acceleration.y; az=accel.acceleration.z;
    gx=gyro.gyro.x; gy=gyro.gyro.y; gz=gyro.gyro.z;
    tempC=temp.temperature;
  }

  StaticJsonDocument<768> doc;
  doc["schema"]="taigun.telemetry.v1";
  doc["source"]="esp32";
  doc["packet"]=packetCounter++;
  doc["uptime_ms"]=now;
  doc["imu_ok"]=imuReady;
  doc["wifi_rssi_dbm"] = WiFi.RSSI();

  JsonObject imu=doc.createNestedObject("imu");
  if (isfinite(ax)) imu["ax_mps2"]=ax;
  if (isfinite(ay)) imu["ay_mps2"]=ay;
  if (isfinite(az)) imu["az_mps2"]=az;
  if (isfinite(gx)) imu["gx_rads"]=gx;
  if (isfinite(gy)) imu["gy_rads"]=gy;
  if (isfinite(gz)) imu["gz_rads"]=gz;
  if (isfinite(tempC)) imu["board_temp_c"]=tempC;

  JsonObject g=doc.createNestedObject("gps");
  g["valid"]=gps.location.isValid();
  if (gps.location.isValid()) {
    g["lat"]=gps.location.lat();
    g["lon"]=gps.location.lng();
  }
  g["speed_kmh"]=gps.speed.isValid() ? gps.speed.kmph() : -1.0;
  g["course_deg"]=gps.course.isValid() ? gps.course.deg() : -1.0;
  g["satellites"]=gps.satellites.isValid() ? gps.satellites.value() : 0;
  if (gps.hdop.isValid()) g["hdop"] = gps.hdop.hdop();
  if (gps.location.isValid()) g["location_age_ms"] = gps.location.age();
  if (gps.date.isValid() && gps.time.isValid()) {
    char iso[25];
    snprintf(iso,sizeof(iso),"%04d-%02d-%02dT%02d:%02d:%02dZ",
      gps.date.year(),gps.date.month(),gps.date.day(),
      gps.time.hour(),gps.time.minute(),gps.time.second());
    g["utc"]=iso;
  }

  char output[768];
  size_t n=serializeJson(doc,output,sizeof(output));
  if (n>0 && WiFi.status()==WL_CONNECTED) {
    udp.beginPacket(LAPTOP_IP,LAPTOP_UDP_PORT);
    udp.write((const uint8_t*)output,n);
    udp.endPacket();
  }
  Serial.println(output);
}
