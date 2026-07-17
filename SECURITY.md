# Security policy

Please report security issues privately to the repository owner instead of
opening a public issue containing credentials or exploit details.

In the default `recorded` mode, Genshin_autoTTS never uploads captured screen
images or recognized text. A remote voice-pack entry may download its declared
audio over HTTPS only after the matching line appears. Downloads have timeout
and size limits and must match the SHA-256 digest in the manifest before they
can enter the cache or be played.

Treat third-party voice-pack manifests as untrusted. Review their license,
source URLs, hashes, speakers, and dialogue text before use. Never include
account identifiers, screenshots, access tokens, cached proprietary audio, or
unlicensed game data in bug reports.

The optional `edge` experiment sends recognized dialogue text to Microsoft's
speech service and produces synthetic audio. It is not used by strict recorded
mode and is not installed as a core dependency.
