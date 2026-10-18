# Room 2.2.5 (transitively used by WorkManager) instantiates generated databases
# through reflection. Its old consumer rule keeps the class but R8 full mode
# removes the default constructor, crashing InitializationProvider at startup.
# Explicitly preserve that constructor, as in the corrected AndroidX rule.
-keep class * extends androidx.room.RoomDatabase {
    <init>();
}
