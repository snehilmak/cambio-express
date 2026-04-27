# OkHttp / Okio keep rules. R8 chokes on a couple of optional
# Conscrypt classes that OkHttp references reflectively but never
# uses on Android — these warnings are safe to suppress.
-dontwarn okhttp3.internal.platform.**
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**
