/*
 * ESP32-CAM Dual-Mode Video Streamer (USB Cable + Wi-Fi)
 * Supports Simultaneous:
 *  1. Direct High-Speed USB Serial Video (COM port @ 921600 baud)
 *  2. Wi-Fi MJPEG Web Server (SoftAP "ESP32-CAM-Vision" @ 192.168.4.1:81/stream)
 */

#include "esp_camera.h"
#include <WiFi.h>
#include "esp_timer.h"
#include "img_converters.h"
#include "Arduino.h"
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"
#include "esp_http_server.h"
#include "camera_pins.h"

// Wi-Fi Access Point Credentials
const char* ap_ssid = "ESP32-CAM-Vision";
const char* ap_password = ""; // Open network for zero friction

// Optional Home/Hotspot Wi-Fi
const char* ssid = "";
const char* password = "";

#define LED_PWM_CHANNEL  7
#define LED_PWM_FREQ     5000
#define LED_PWM_RES      8

httpd_handle_t stream_httpd = NULL;
httpd_handle_t camera_httpd = NULL;
static int flash_brightness = 0;

#define PART_BOUNDARY "123456789000000000000987654321"
static const char* _STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char* _STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
static const char* _STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

void set_flash(int brightness) {
  flash_brightness = constrain(brightness, 0, 255);
#if defined(ESP_ARDUINO_VERSION_MAJOR) && (ESP_ARDUINO_VERSION_MAJOR >= 3)
  ledcWrite(FLASH_LED_PIN, flash_brightness);
#else
  ledcWrite(LED_PWM_CHANNEL, flash_brightness);
#endif
}

// ==========================================
// Wi-Fi Stream Handlers
// ==========================================
static esp_err_t stream_handler(httpd_req_t *req) {
  camera_fb_t *fb = NULL;
  esp_err_t res = ESP_OK;
  char part_buf[64];

  res = httpd_resp_set_type(req, _STREAM_CONTENT_TYPE);
  if (res != ESP_OK) return res;
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");

  while (true) {
    fb = esp_camera_fb_get();
    if (!fb) {
      res = ESP_FAIL;
    } else {
      if (fb->format == PIXFORMAT_JPEG) {
        size_t hlen = snprintf(part_buf, 64, _STREAM_PART, fb->len);
        res = httpd_resp_send_chunk(req, part_buf, hlen);
        if (res == ESP_OK) {
          res = httpd_resp_send_chunk(req, (const char *)fb->buf, fb->len);
        }
        if (res == ESP_OK) {
          res = httpd_resp_send_chunk(req, _STREAM_BOUNDARY, strlen(_STREAM_BOUNDARY));
        }
      }
      esp_camera_fb_return(fb);
    }
    if (res != ESP_OK) break;
  }
  return res;
}

static esp_err_t capture_handler(httpd_req_t *req) {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    httpd_resp_send_500(req);
    return ESP_FAIL;
  }
  httpd_resp_set_type(req, "image/jpeg");
  httpd_resp_set_hdr(req, "Content-Disposition", "inline; filename=capture.jpg");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  esp_err_t res = httpd_resp_send(req, (const char *)fb->buf, fb->len);
  esp_camera_fb_return(fb);
  return res;
}

static esp_err_t led_handler(httpd_req_t *req) {
  char buf[64];
  int state = 0;
  int brightness = 255;
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  httpd_resp_set_type(req, "application/json");

  if (httpd_req_get_url_query_len(req) > 0) {
    if (httpd_req_get_url_query_str(req, buf, sizeof(buf)) == ESP_OK) {
      char param[16];
      if (httpd_query_key_value(buf, "state", param, sizeof(param)) == ESP_OK) state = atoi(param);
      if (httpd_query_key_value(buf, "brightness", param, sizeof(param)) == ESP_OK) brightness = atoi(param);
    }
  }
  set_flash(state > 0 ? brightness : 0);
  char json_res[128];
  snprintf(json_res, sizeof(json_res), "{\"success\":true,\"state\":%d,\"brightness\":%d}", (flash_brightness > 0 ? 1 : 0), flash_brightness);
  httpd_resp_send(req, json_res, strlen(json_res));
  return ESP_OK;
}

static esp_err_t status_handler(httpd_req_t *req) {
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  httpd_resp_set_type(req, "application/json");
  char json[256];
  snprintf(json, sizeof(json),
    "{\"mode\":\"dual\",\"ip\":\"%s\",\"uptime_sec\":%lu,\"heap\":%u,\"flash\":%d}",
    WiFi.getMode() == WIFI_MODE_AP ? WiFi.softAPIP().toString().c_str() : WiFi.localIP().toString().c_str(),
    millis() / 1000,
    ESP.getFreeHeap(),
    flash_brightness
  );
  httpd_resp_send(req, json, strlen(json));
  return ESP_OK;
}

void startCameraServer() {
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.server_port = 80;
  config.ctrl_port = 32768;

  httpd_uri_t capture_uri = { .uri = "/capture", .method = HTTP_GET, .handler = capture_handler, .user_ctx = NULL };
  httpd_uri_t led_uri     = { .uri = "/led",     .method = HTTP_GET, .handler = led_handler,     .user_ctx = NULL };
  httpd_uri_t status_uri  = { .uri = "/status",  .method = HTTP_GET, .handler = status_handler,  .user_ctx = NULL };

  if (httpd_start(&camera_httpd, &config) == ESP_OK) {
    httpd_register_uri_handler(camera_httpd, &capture_uri);
    httpd_register_uri_handler(camera_httpd, &led_uri);
    httpd_register_uri_handler(camera_httpd, &status_uri);
  }

  config.server_port = 81;
  config.ctrl_port = 32769;
  httpd_uri_t stream_uri = { .uri = "/stream", .method = HTTP_GET, .handler = stream_handler, .user_ctx = NULL };

  if (httpd_start(&stream_httpd, &config) == ESP_OK) {
    httpd_register_uri_handler(stream_httpd, &stream_uri);
  }
}

void setup() {
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0); // Disable brownout detector

  // High-Speed USB Serial for cable streaming
  Serial.begin(921600);
  delay(100);

  // Initialize Flash LED
#if defined(ESP_ARDUINO_VERSION_MAJOR) && (ESP_ARDUINO_VERSION_MAJOR >= 3)
  ledcAttach(FLASH_LED_PIN, LED_PWM_FREQ, LED_PWM_RES);
#else
  ledcSetup(LED_PWM_CHANNEL, LED_PWM_FREQ, LED_PWM_RES);
  ledcAttachPin(FLASH_LED_PIN, LED_PWM_CHANNEL);
#endif

  set_flash(40);
  delay(100);
  set_flash(0);

  pinMode(STATUS_LED_PIN, OUTPUT);
  digitalWrite(STATUS_LED_PIN, HIGH);

  // Camera Configuration
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  
  // 10MHz clock frequency ensures reliable data across all OV2640 modules
  config.xclk_freq_hz = 10000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_QVGA; // 320x240 for high USB & Wi-Fi frame rate
  config.jpeg_quality = 14;
  config.fb_count = 2;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    return;
  }

  sensor_t *s = esp_camera_sensor_get();
  if (s) {
    s->set_brightness(s, 1);
    s->set_contrast(s, 1);
    s->set_saturation(s, 0);
    s->set_whitebal(s, 1);
    s->set_awb_gain(s, 1);
    s->set_exposure_ctrl(s, 1);
    s->set_gain_ctrl(s, 1);
    s->set_agc_gain(s, 2);
    s->set_vflip(s, 1);
  }

  // Warmup cycle (discard black frames on boot)
  for (int i = 0; i < 6; i++) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (fb) esp_camera_fb_return(fb);
    delay(40);
  }

  // Start Wi-Fi SoftAP
  WiFi.mode(WIFI_AP);
  WiFi.softAP(ap_ssid);
  startCameraServer();

  digitalWrite(STATUS_LED_PIN, LOW); // On = Ready
}

void loop() {
  // Check for commands from PC over USB
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd == "L1") set_flash(255);
    else if (cmd == "L0") set_flash(0);
    else if (cmd.startsWith("LB")) set_flash(cmd.substring(2).toInt());
  }

  // Capture frame & stream over USB Serial
  camera_fb_t *fb = esp_camera_fb_get();
  if (fb) {
    if (fb->format == PIXFORMAT_JPEG && fb->len > 0) {
      uint8_t header[8];
      header[0] = 0xFF;
      header[1] = 0xAA;
      header[2] = 0x55;
      header[3] = 0xFF;
      
      uint32_t len = fb->len;
      header[4] = (uint8_t)(len & 0xFF);
      header[5] = (uint8_t)((len >> 8) & 0xFF);
      header[6] = (uint8_t)((len >> 16) & 0xFF);
      header[7] = (uint8_t)((len >> 24) & 0xFF);

      Serial.write(header, 8);
      Serial.write(fb->buf, fb->len);
    }
    esp_camera_fb_return(fb);
  }

  delay(12); // ~30 FPS limit
}
