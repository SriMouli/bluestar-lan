# Blue Star LAN

Local network control and live status for Blue Star Smart ACs, with a Python client and Home Assistant integration.

Blue Star LAN uses your Blue Star account during setup to obtain the paired ACs' LAN keys and model capabilities. After setup, the Home Assistant integration receives status and sends commands directly over the local network. Each AC gets its own climate entity, with power, supported HVAC modes, setpoint, room temperature, and availability.

## Compatibility

- Home Assistant 2026.11 or later for Marketplace installation.
- ACs paired in [Blue Star Smart AC](https://play.google.com/store/apps/details?id=com.bluestarindia.bluesmart) that advertise a supported LAN profile. Blue Star's similarly named CoolAutomation app uses a different platform.
- Celsius display mode. Home Assistant and the ACs need to be on a network that delivers the ACs' UDP broadcasts on port 44542 to Home Assistant. Check VLAN isolation or guest Wi-Fi settings if a unit stays unavailable.
- The first version covers the basic climate controls. Fan speed, swing, presets, and usage history require separate model validation.

## Install in Home Assistant

1. Open **Settings → Marketplace → Add from link** and enter `https://github.com/SriMouli/bluestar-lan`. Connect GitHub if Marketplace asks.
2. Select **Blue Star LAN → Install**, then sign in with the account used in the Blue Star Smart AC app. The integration adds the supported units on that account.
3. Use **Reconfigure** under **Settings → Devices & services → Blue Star LAN** to refresh LAN keys or add newly paired units. The integration stores unit keys and capabilities in its config entry. It does not retain the account password or cloud session.

This is a community integration. If you report a problem, include the model, firmware, Home Assistant version and affected function. Leave out account details, LAN keys and configuration storage files.

## Use from Python

From a checkout on macOS or Linux with Python 3.11 or later:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m custom_components.bluestar_lan list
.venv/bin/python -m custom_components.bluestar_lan status UNIT_ID
.venv/bin/python -m custom_components.bluestar_lan set-temperature UNIT_ID 24
```

The client prompts for your Blue Star login. To reuse an existing credentials file, pass `--credentials-file /path/to/credentials.json` before the action. Use a private JSON file containing `username` and `password` and set its permissions to `0600`. The Python commands provision keys at startup and listen on the same UDP port as the Home Assistant integration. Run them on a different host if Home Assistant is already listening there.

## Development

```sh
.venv/bin/python -m unittest discover -s tests -v
```

The project is distributed under the [MIT license](LICENSE).

Built with Codex. Developed on an Apple Mac mini (M6).
