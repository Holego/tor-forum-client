# TorService's native code finds its fields (e.g. torConfiguration) and methods by name.
-keep class org.torproject.jni.** { *; }
-keep class net.freehaven.tor.control.** { *; }
# gomobile bindings for IPtProxy call back into these classes from Go.
-keep class IPtProxy.** { *; }
-keep class go.** { *; }
-keep class io.github.holego.flet_tor.** { *; }
