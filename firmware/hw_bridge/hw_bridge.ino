// Hardware Studio - Bridge Firmware v1
// Ek baar board me flash karo, phir app/PC se text commands se pins control karo.
// Serial: 115200 baud, har command ek line (\n se khatam)
//
//   PING                  -> PONG HWBRIDGE 1
//   MODE <pin> IN|OUT|PULLUP
//   DW <pin> <0|1>        digital write
//   DR <pin>              -> DR <pin> <0|1>
//   AR <pin>              -> AR <pin> <0..1023>
//   PWM <pin> <0..255>
//   SERVO <pin> <0..180>
//   STREAM <pin> <ms>     analog value baar-baar bhejo (STREAM OFF band karne ke liye)
// Pin "13" ya "A0" dono tarah likh sakte ho.

#include <Servo.h>

Servo servos[20];
bool attached[20];
String line;
int streamPin = -1;
unsigned long streamMs = 0, lastStream = 0;

int parsePin(String s) {
  s.trim();
  if (s.length() > 0 && (s[0] == 'A' || s[0] == 'a')) return A0 + s.substring(1).toInt();
  return s.toInt();
}

String tok(String &s) {
  s.trim();
  int i = s.indexOf(' ');
  String t;
  if (i < 0) { t = s; s = ""; }
  else { t = s.substring(0, i); s = s.substring(i + 1); }
  return t;
}

void handle(String l) {
  l.trim();
  if (l.length() == 0) return;
  String cmd = tok(l);
  cmd.toUpperCase();
  if (cmd == "PING") {
    Serial.println(F("PONG HWBRIDGE 1"));
  } else if (cmd == "MODE") {
    int p = parsePin(tok(l));
    String m = tok(l); m.toUpperCase();
    pinMode(p, m == "OUT" ? OUTPUT : (m == "PULLUP" ? INPUT_PULLUP : INPUT));
    Serial.println(F("OK"));
  } else if (cmd == "DW") {
    int p = parsePin(tok(l));
    int v = tok(l).toInt();
    pinMode(p, OUTPUT);
    digitalWrite(p, v ? HIGH : LOW);
    Serial.println(F("OK"));
  } else if (cmd == "DR") {
    int p = parsePin(tok(l));
    Serial.print(F("DR ")); Serial.print(p); Serial.print(' ');
    Serial.println(digitalRead(p));
  } else if (cmd == "AR") {
    int p = parsePin(tok(l));
    Serial.print(F("AR ")); Serial.print(p); Serial.print(' ');
    Serial.println(analogRead(p));
  } else if (cmd == "PWM") {
    int p = parsePin(tok(l));
    int v = constrain(tok(l).toInt(), 0, 255);
    pinMode(p, OUTPUT);
    analogWrite(p, v);
    Serial.println(F("OK"));
  } else if (cmd == "SERVO") {
    int p = parsePin(tok(l));
    int a = constrain(tok(l).toInt(), 0, 180);
    if (p >= 0 && p < 20) {
      if (!attached[p]) { servos[p].attach(p); attached[p] = true; }
      servos[p].write(a);
      Serial.println(F("OK"));
    } else Serial.println(F("ERR pin"));
  } else if (cmd == "STREAM") {
    String a = tok(l);
    String b = a; b.toUpperCase();
    if (b == "OFF") { streamPin = -1; Serial.println(F("OK")); }
    else {
      streamPin = parsePin(a);
      streamMs = max(20, tok(l).toInt());
      Serial.println(F("OK"));
    }
  } else {
    Serial.println(F("ERR unknown"));
  }
}

void setup() {
  Serial.begin(115200);
  Serial.println(F("READY HWBRIDGE 1"));
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') { handle(line); line = ""; }
    else if (c != '\r' && line.length() < 80) line += c;
  }
  if (streamPin >= 0 && millis() - lastStream >= streamMs) {
    lastStream = millis();
    Serial.print(F("AR ")); Serial.print(streamPin); Serial.print(' ');
    Serial.println(analogRead(streamPin));
  }
}
