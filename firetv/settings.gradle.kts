/*
 * Top-level Gradle settings for the DineroBook TV Fire TV app.
 *
 * The Android project is intentionally isolated under firetv/ so the
 * Flask backend's CI never has to touch the Android toolchain. Open
 * this directory directly in Android Studio (File → Open → firetv/)
 * to build, sign, and export an APK / AAB for the Amazon Appstore.
 */
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "DineroBookTV"
include(":app")
