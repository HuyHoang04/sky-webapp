#include <Arduino.h>
#include <HardwareSerial.h>
#include <TinyGPSPlus.h>
#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <WiFiClientSecure.h>

// ================== WEBSOCKET CONFIG ==================
const char* websocket_host = "https://kanisha-unannexable-laraine.ngrok-free.dev"; // Thay bằng URL ngrok của bạn (không cần https://)
const int websocket_port = 443;

WebSocketsClient webSocket;
StaticJsonDocument<200> jsonDoc;

// Các khai báo khác giữ nguyên như cũ
#define SIM_TX 12
#define SIM_RX 13
#define GPS_TX 27
#define GPS_RX 26

HardwareSerial simSerial(2);
HardwareSerial gpsSerial(1);

TinyGPSPlus gps;

#define SIM_BAUDRATE 9600
#define GPS_BAUDRATE 9600
#define PHONE_NUMBER "+84342138992"

const int buttonPin = 23;
const int ledR = 15;
const int ledG = 2;

// Các biến hệ thống giữ nguyên
enum SystemState { SLEEP, READY, CALLING, IN_CALL };
SystemState systemState = SLEEP;

bool buttonStableState = HIGH;
bool lastReading = HIGH;
unsigned long lastDebounceTime = 0;
const unsigned long DEBOUNCE_MS = 50;
unsigned long callBlinkTime = 0;
bool ledRedState = false;
unsigned int buttonPressCount = 0;

// WebSocket callback
void webSocketEvent(WStype_t type, uint8_t * payload, size_t length) {
    switch(type) {
        case WStype_DISCONNECTED:
            Serial.println("[WS] Disconnected!");
            break;
        case WStype_CONNECTED:
            Serial.println("[WS] Connected!");
            // Gửi thông tin thiết bị
            jsonDoc.clear();
            jsonDoc["type"] = "device_info";
            jsonDoc["device_id"] = "lifebuoy-1";
            jsonDoc["device_type"] = "lifebuoy";
            String json;
            serializeJson(jsonDoc, json);
            webSocket.sendTXT(json);
            break;
        case WStype_TEXT:
            handleWebSocketMessage(payload, length);
            break;
    }
}

void handleWebSocketMessage(uint8_t * payload, size_t length) {
    String message = String((char*)payload);
    DeserializationError error = deserializeJson(jsonDoc, message);
    
    if (error) {
        Serial.println("JSON parsing failed!");
        return;
    }

    const char* type = jsonDoc["type"];
    
    if (strcmp(type, "accept_call") == 0) {
        // No action needed as call is already connected when initiated from buoy
    } else if (strcmp(type, "end_call") == 0) {
        endCall();
    }
}

// Function to send GPS data
void sendGPSData() {
    if (gps.location.isValid()) {
        jsonDoc.clear();
        jsonDoc["type"] = "gps_update";
        jsonDoc["device_id"] = "lifebuoy-1";
        jsonDoc["latitude"] = gps.location.lat();
        jsonDoc["longitude"] = gps.location.lng();
        jsonDoc["altitude"] = gps.altitude.meters();
        jsonDoc["speed"] = gps.speed.kmph();
        jsonDoc["satellites"] = gps.satellites.value();
        jsonDoc["hdop"] = gps.hdop.hdop();
        
        String json;
        serializeJson(jsonDoc, json);
        webSocket.sendTXT(json);
    }
}

// Function to notify incoming call
void notifyIncomingCall() {
    jsonDoc.clear();
    jsonDoc["type"] = "incoming_call";
    jsonDoc["device_id"] = "lifebuoy-1";
    jsonDoc["phoneNumber"] = PHONE_NUMBER;
    
    String json;
    serializeJson(jsonDoc, json);
    webSocket.sendTXT(json);
}

// Function to notify call status
void notifyCallStatus(const char* status) {
    jsonDoc.clear();
    jsonDoc["type"] = "call_status";
    jsonDoc["device_id"] = "lifebuoy-1";
    jsonDoc["status"] = status;
    
    String json;
    serializeJson(jsonDoc, json);
    webSocket.sendTXT(json);
}

// Các hàm tiện ích giữ nguyên
void printLeft(String msg) { Serial.printf("[SYS] %-50s\n", msg.c_str()); }
void printRight(String msg) { Serial.printf("[GPS] %s\n", msg.c_str()); }
void printError(String msg) { Serial.printf("[LỖI] %s\n", msg.c_str()); }

// Các hàm xử lý SIM giữ nguyên
void simSendAT(String cmd) {
    simSerial.println(cmd);
    Serial.print("SIM>> ");
    Serial.println(cmd);
}

bool simCheckResponse(String expected, unsigned long timeout = 2000) {
    unsigned long start = millis();
    String resp = "";
    while (millis() - start < timeout) {
        while (simSerial.available()) resp += (char)simSerial.read();
    }
    resp.trim();
    if (resp.length() > 0) Serial.println("RESP: " + resp);
    return resp.indexOf(expected) != -1;
}

// Các hàm xử lý LED giữ nguyên
void fadeLED(int fromR, int fromG, int toR, int toG) {
    for (int i = 0; i <= 255; i += 15) {
        analogWrite(ledR, map(i, 0, 255, fromR, toR));
        analogWrite(ledG, map(i, 0, 255, fromG, toG));
        delay(10);
    }
}

void updateLED() {
    switch (systemState) {
        case SLEEP:
            digitalWrite(ledR, LOW);
            digitalWrite(ledG, LOW);
            break;
        case READY:
            digitalWrite(ledR, LOW);
            digitalWrite(ledG, HIGH);
            break;
        case CALLING:
            if (millis() - callBlinkTime > 500) {
                ledRedState = !ledRedState;
                digitalWrite(ledR, ledRedState ? HIGH : LOW);
                callBlinkTime = millis();
            }
            digitalWrite(ledG, LOW);
            break;
        case IN_CALL:
            digitalWrite(ledR, HIGH);
            digitalWrite(ledG, LOW);
            break;
    }
}

// Xử lý nút nhấn giữ nguyên
bool isButtonPressed() {
    bool reading = digitalRead(buttonPin);
    bool pressedEvent = false;

    if (reading != lastReading) lastDebounceTime = millis();
    if ((millis() - lastDebounceTime) > DEBOUNCE_MS) {
        if (reading != buttonStableState) {
            buttonStableState = reading;
            if (buttonStableState == LOW) pressedEvent = true;
        }
    }
    lastReading = reading;
    return pressedEvent;
}

// Hàm kiểm tra SIM giữ nguyên
bool checkSIMReady(bool verbose = true) {
    simSendAT("AT");
    if (!simCheckResponse("OK")) { if (verbose) printError("Không phản hồi lệnh AT"); return false; }

    simSendAT("AT+CPIN?");
    if (!simCheckResponse("READY")) { if (verbose) printError("SIM chưa sẵn sàng!"); return false; }

    simSendAT("AT+CSQ");
    simCheckResponse("+CSQ:");

    simSendAT("AT+CREG?");
    if (!simCheckResponse(",1")) { if (verbose) printError("SIM chưa đăng ký mạng."); return false; }

    simSendAT("AT+COPS?");
    simCheckResponse("+COPS:");

    if (verbose) printLeft("QUY TRÌNH KIỂM TRA SIM HOÀN TẤT");
    return true;
}

// Xử lý GPS giữ nguyên
void readGPSData() {
    while (gpsSerial.available()) {
        gps.encode(gpsSerial.read());
    }

    static unsigned long lastDisplay = 0;
    if (millis() - lastDisplay >= 1000) {
        lastDisplay = millis();

        if (gps.location.isValid()) {
            Serial.println("───────────── [DỮ LIỆU GPS U-BLOX NEO-7N] ─────────────");
            Serial.printf("⏱ Thời gian UTC: %02d:%02d:%02d\n", gps.time.hour(), gps.time.minute(), gps.time.second());
            Serial.printf("📍 Vĩ độ: %.6f°\n", gps.location.lat());
            Serial.printf("📍 Kinh độ: %.6f°\n", gps.location.lng());
            Serial.printf("📏 Độ cao: %.2f m\n", gps.altitude.meters());
            Serial.printf("🚗 Tốc độ: %.2f km/h\n", gps.speed.kmph());
            Serial.printf("🧭 Hướng di chuyển: %.2f°\n", gps.course.deg());
            Serial.printf("📡 Số vệ tinh: %d\n", gps.satellites.value());
            Serial.printf("🎯 HDOP: %.2f\n", gps.hdop.hdop());
            Serial.println("───────────────────────────────────────────────────────");
        } else {
            printRight("Đang tìm tín hiệu GPS...");
        }
    }
}

// Hàm xử lý cuộc gọi đã được cập nhật
void makeCall() {
    printLeft("Chuẩn bị thực hiện cuộc gọi...");
    if (!checkSIMReady(false)) {
        printError("SIM không có mạng, không thể gọi!");
        return;
    }
    simSendAT("ATD" + String(PHONE_NUMBER) + ";");
    systemState = CALLING;
    notifyCallStatus("calling");
}

void endCall() {
    printLeft("Đang kết thúc cuộc gọi...");
    simSendAT("AT+CHUP");
    delay(500);
    simSendAT("ATH");
    delay(300);
    systemState = READY;
    notifyCallStatus("ended");
    printLeft("✅ Cuộc gọi đã được ngắt hoàn toàn.");
}

// Hàm khởi tạo phần cứng giữ nguyên
void initHardware() {
    pinMode(buttonPin, INPUT_PULLUP);
    pinMode(ledR, OUTPUT);
    pinMode(ledG, OUTPUT);
    digitalWrite(ledR, LOW);
    digitalWrite(ledG, LOW);

    Serial.begin(115200);
    simSerial.begin(SIM_BAUDRATE, SERIAL_8N1, SIM_RX, SIM_TX);
    gpsSerial.begin(GPS_BAUDRATE, SERIAL_8N1, GPS_RX, GPS_TX);

    printLeft("Khởi tạo phần cứng hoàn tất.");
}

// Setup WebSocket với SSL
void setupWebSocket() {
    // Bắt đầu kết nối WebSocket với SSL
    webSocket.beginSSL(websocket_host, websocket_port, "/socket.io/?EIO=4");
    webSocket.onEvent(webSocketEvent);
    webSocket.setReconnectInterval(5000);
}

// Khởi động hệ thống
void initialCheck() {
    delay(1000);
    checkSIMReady(true);
    delay(800);
    printLeft("Cấu hình âm thanh SIM...");
    simSendAT("AT+CLVL=90");
    simCheckResponse("OK");
    delay(300);
    printLeft("✅ Hệ thống đã sẵn sàng.");
    systemState = READY;
}

// Setup
void setup() {
    initHardware();
    setupWebSocket();
    printLeft("System initialized. Sleep mode.");
    initialCheck();
}

// Main loop
void loop() {
    webSocket.loop();
    
    if (isButtonPressed()) {
        buttonPressCount++;
        printLeft("Nút được nhấn lần thứ " + String(buttonPressCount));

        switch (systemState) {
            case SLEEP:
                systemState = READY;
                fadeLED(0, 0, 0, 255);
                printLeft("System READY");
                break;
            case READY:
                fadeLED(0, 255, 255, 0);
                makeCall();
                break;
            case CALLING:
            case IN_CALL:
                fadeLED(255, 0, 0, 255);
                endCall();
                break;
        }
    }

    // Xử lý dữ liệu từ SIM
    if (simSerial.available()) {
        String data = simSerial.readString();
        if (data.indexOf("VOICE CALL: BEGIN") != -1) {
            systemState = IN_CALL;
            printLeft("📞 Cuộc gọi đã kết nối, cấu hình âm thanh...");
            simSendAT("AT+CSDVC=3");
            simSendAT("AT+CTXMICGAIN=4000");
            simSendAT("AT+CRXVOL=4000");
            notifyCallStatus("connected");
            printLeft("✅ Cấu hình âm thanh hoàn tất.");
        }
        if (data.indexOf("NO CARRIER") != -1 || data.indexOf("VOICE CALL: END") != -1) {
            systemState = READY;
            notifyCallStatus("ended");
            printLeft("📴 Cuộc gọi kết thúc.");
        }
        // Check for incoming call
        if (data.indexOf("RING") != -1) {
            notifyIncomingCall();
        }
    }

    updateLED();
    readGPSData();
    
    // Send GPS data every 2 seconds when in call
    static unsigned long lastGPSSend = 0;
    if (systemState == IN_CALL && millis() - lastGPSSend >= 2000) {
        sendGPSData();
        lastGPSSend = millis();
    }
}