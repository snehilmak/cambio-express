/*
 * Root project build file. Plugin versions are pinned here so every
 * sub-module (currently just :app) sees the same toolchain.
 */
plugins {
    id("com.android.application") version "8.5.0" apply false
    id("org.jetbrains.kotlin.android") version "1.9.22" apply false
}
