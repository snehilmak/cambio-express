/*
 * DineroBookTV — the Fire TV / Google TV companion app.
 *
 * Single-Activity-per-screen WebView shell. Authenticates via the
 * pair-code flow (POST /api/tv-pair/redeem) and points its WebView
 * at the per-device URL the backend hands back.
 *
 * Min SDK 22 (Android 5.1) covers Fire TV Stick gen 2+. Target SDK
 * 34 is required by the Amazon Appstore for new submissions and
 * updates as of 2024.
 */
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.dinerobook.tv"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.dinerobook.tv"
        minSdk        = 22
        targetSdk     = 34
        versionCode   = 1
        versionName   = "1.0.0"

        // The base URL the redeem POST + WebView hit. Override per
        // build flavor by setting BASE_URL in local.properties:
        //   BASE_URL="https://staging.dinerobook.onrender.com"
        // Default points at the production deployment.
        val baseUrl = providers.gradleProperty("BASE_URL")
            .orElse("https://dinerobook.onrender.com")
            .get()
        buildConfigField("String", "BASE_URL", "\"$baseUrl\"")
    }

    buildTypes {
        debug {
            isDebuggable = true
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
        }
        release {
            // Operator-supplied signing config — see firetv/README.md
            // "Sign for release" for keystore generation steps.
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }

    buildFeatures {
        viewBinding = true
        buildConfig = true
    }

    sourceSets {
        getByName("main").java.srcDirs("src/main/kotlin")
    }
}

dependencies {
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")
    implementation("androidx.leanback:leanback:1.0.0")

    // HTTP + JSON for the pair-code redeem call. OkHttp is industry
    // standard on Android; org.json is bundled with the platform so
    // we don't need a heavier JSON library for two response keys.
    implementation("com.squareup.okhttp3:okhttp:4.12.0")

    // Coroutines for cleanly running the redeem call off the main
    // thread without leaking Dispatchers / boilerplate.
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")
}
