# CPAL Android headless support

Vendored from the cpal 0.18.2 crates.io release (Apache-2.0; see LICENSE).
The android-headless feature is enabled only for the Termux voice helper.
It exposes the default device without Java enumeration and obtains the mixer
buffer count from the native AAudio stream instead of Android Java system properties.
The existing AAudio callbacks, timing conversions, error handling and ownership remain.
Default builds retain upstream behavior.
