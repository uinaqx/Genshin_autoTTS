# Security policy

Please report security issues privately to the repository owner instead of
opening a public issue containing credentials or exploit details.

Screen capture, OCR, and speaker-to-voice routing run locally. In the default
`volcengine` mode, the selected cloud service receives only the stabilized
dialogue text, voice identifier, and synthesis parameters. Speaker names and
screen images are not included in cloud TTS requests.

Cloud API credentials are encrypted with Windows DPAPI for the current user and
stored in `credentials.dat`; they are never written to `config.json`. Supported
environment variables take precedence and allow credentials to remain
diskless. Do not attach `credentials.dat`, environment dumps, access tokens, or
full runtime logs to an issue.

Cloud requests use built-in HTTPS endpoints, bounded response sizes, timeouts,
and limited retries. Synthesized audio is cached locally to reduce data
exposure, latency, and repeated billing.

Treat third-party voice-pack manifests as untrusted. Review their license,
source URLs, hashes, speakers, and dialogue text before use. Never include
account identifiers, screenshots, access tokens, cached proprietary audio, or
unlicensed game data in bug reports.

The `recorded` compatibility mode may download its declared audio over HTTPS
only after the matching line appears. Downloads have timeout and size limits
and must match the SHA-256 digest in the manifest before they can enter the
cache or be played. The optional `edge` experiment sends dialogue text to
Microsoft's speech service and is not installed as a core dependency.
