# Hardware Studio (EXE)
Kisi bhi board (Uno, Nano, Mega, ESP32, ESP8266, Pico, STM32...) me code compile + upload, pins control, serial plotter, aur AI assistant.

## GitHub se EXE banana
1. Is folder ko naye GitHub repo me push karo.
2. Actions tab -> "Build EXE" -> Run workflow.
3. Artifact `HardwareStudio-exe` download karo.

## Use
1. Device tab: board + port chuno, "Board core install karo" (pehli baar).
2. AI tab: API key daalo (Anthropic ya Groq), jo chahiye maango, "Code editor me daalo".
3. Code tab: "Compile + Upload".
4. Pins tab: "Bridge firmware daalo" -> upload, phir pins/PWM/servo control.

Local run: `pip install -r requirements.txt && python app.py`
