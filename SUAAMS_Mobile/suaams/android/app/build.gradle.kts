import java.io.FileInputStream
import java.util.Properties

plugins {
    id("com.android.application")
    id("com.google.gms.google-services")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Release signing key, from android/key.properties + android/suaams-release.jks.
// Neither is in git (android/.gitignore); back both up. The key is load-
// bearing twice over: freeRASP's integrity check expects THIS certificate
// (signingCertHashes in lib/core/services/security_service.dart), and
// ANDROID_ID -- what device binding stores -- is scoped to the signing key,
// so a new key gives every phone a new ID and un-binds every student.
val keystorePropertiesFile = rootProject.file("key.properties")
val keystoreProperties = Properties().apply {
    if (keystorePropertiesFile.exists()) load(FileInputStream(keystorePropertiesFile))
}

// A release build without the key used to fall back to the debug key. Its
// certificate doesn't match signingCertHashes, so freeRASP flagged the app
// as tampered and check-in was refused on every phone. Stop the build
// instead. Debug builds don't need the key.
val buildingRelease = gradle.startParameter.taskNames.any { it.contains("Release", ignoreCase = true) }
if (buildingRelease && !keystorePropertiesFile.exists()) {
    throw GradleException(
        "Release build needs android/key.properties and the release keystore " +
        "(suaams-release.jks). They are not in git: copy them from your backup."
    )
}

android {
    namespace = "com.suaams.mobile"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
        // flutter_local_notifications' Android implementation uses java.time
        // APIs that need desugaring to run on API levels below 26 -- without
        // this, Gradle's checkDebugAarMetadata task fails the build outright
        // rather than producing a broken APK.
        isCoreLibraryDesugaringEnabled = true
    }

    defaultConfig {
        applicationId = "com.suaams.mobile"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        if (keystorePropertiesFile.exists()) {
            create("release") {
                keyAlias = keystoreProperties["keyAlias"] as String
                keyPassword = keystoreProperties["keyPassword"] as String
                storeFile = file(keystoreProperties["storeFile"] as String)
                storePassword = keystoreProperties["storePassword"] as String
            }
        }
    }

    buildTypes {
        release {
            // The release key (see the top of this file). Only absent when
            // no release task is running, so debug builds still configure.
            signingConfig = signingConfigs.findByName("release")
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}

dependencies {
    // Required by isCoreLibraryDesugaringEnabled above.
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")
}
