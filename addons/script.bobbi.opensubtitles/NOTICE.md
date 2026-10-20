# Provenance and scope

Derived from the private AM6B manual subtitle integration (GPL-2.0-or-later),
modified for bobbi on 2026-10-19. The REST protocol was researched against
`opensubtitles-dev/service.subtitles.opensubtitles-com` 1.0.91, commit
`7acfa8f2932a0155ba921212882baa0fade05890`; reference archive SHA256
`1593b3ec0a64affdfda4bd8346c40e40d20a6a0b5b8f55cf645d7023b50d6d76`.
This is independently maintained, not the unmodified official provider.

The previous integration's public upstream application key and private proxy
default are deliberately NOT included. Supply your own OpenSubtitles API key
in this add-on's settings; quotas and authentication remain provider-controlled.
No cloud login, media URL, user account, API key or authentication token is
shipped. Core/runtime policies retain their own license declarations.

Search and download are explicit user actions. There is no service, updater,
automatic subtitle application, video/audio download or cloud submission.
Candidates are selected for identity and Chinese text quality, not certified
synchronization. Manual delay/close choices are not overwritten.

Actual native Player.BobiState plus native BrowseSubtitle owns application.
Stock Kodi cannot impersonate that contract. The unified host profile chooses
the current native root; only the hash-verified deployed CE F9 ABI uses the
documented legacy root. Other native hosts use the bobbi profile. Credentials
belong to this user's local profile and must not enter distributions.
