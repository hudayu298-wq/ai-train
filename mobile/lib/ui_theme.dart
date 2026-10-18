import 'package:flutter/material.dart';

abstract final class AppColors {
  static const background = Color(0xfff7f8fb);
  static const surface = Colors.white;
  static const ink = Color(0xff1b202b);
  static const muted = Color(0xff747d8e);
  static const line = Color(0xffe6e9ef);
  static const primary = Color(0xff3c5ddd);
  static const soft = Color(0xfff0f3f9);
  static const selected = Color(0xffedf1ff);
}

ThemeData buildAppTheme() => ThemeData(
  useMaterial3: true,
  colorScheme: ColorScheme.fromSeed(seedColor: AppColors.primary).copyWith(
    primary: AppColors.primary,
    onPrimary: Colors.white,
    secondary: const Color(0xff59667e),
    tertiary: const Color(0xff8971b2),
    surface: AppColors.surface,
    onSurface: AppColors.ink,
    outline: const Color(0xffccd2dd),
    outlineVariant: AppColors.line,
  ),
  scaffoldBackgroundColor: AppColors.background,
  textTheme: const TextTheme(
    titleLarge: TextStyle(
      fontSize: 19,
      fontWeight: FontWeight.w600,
      color: AppColors.ink,
    ),
    titleMedium: TextStyle(
      fontSize: 15,
      fontWeight: FontWeight.w600,
      color: AppColors.ink,
    ),
    bodyLarge: TextStyle(fontSize: 14, height: 1.55, color: AppColors.ink),
    bodyMedium: TextStyle(fontSize: 13, height: 1.5, color: AppColors.ink),
    bodySmall: TextStyle(fontSize: 12, height: 1.4, color: AppColors.muted),
  ),
  appBarTheme: const AppBarTheme(
    backgroundColor: AppColors.surface,
    foregroundColor: AppColors.ink,
    elevation: 0,
    scrolledUnderElevation: 0,
    centerTitle: false,
    titleTextStyle: TextStyle(
      fontSize: 18,
      fontWeight: FontWeight.w600,
      color: AppColors.ink,
    ),
    shape: Border(bottom: BorderSide(color: AppColors.line)),
  ),
  cardTheme: CardThemeData(
    color: AppColors.surface,
    elevation: 0,
    margin: EdgeInsets.zero,
    shape: RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(14),
      side: const BorderSide(color: AppColors.line),
    ),
  ),
  inputDecorationTheme: InputDecorationTheme(
    filled: true,
    fillColor: const Color(0xfffbfcfe),
    contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
    labelStyle: const TextStyle(fontSize: 13, color: AppColors.muted),
    hintStyle: const TextStyle(fontSize: 14, color: AppColors.muted),
    border: OutlineInputBorder(
      borderRadius: BorderRadius.circular(10),
      borderSide: const BorderSide(color: AppColors.line),
    ),
    enabledBorder: OutlineInputBorder(
      borderRadius: BorderRadius.circular(10),
      borderSide: const BorderSide(color: AppColors.line),
    ),
    focusedBorder: OutlineInputBorder(
      borderRadius: BorderRadius.circular(10),
      borderSide: const BorderSide(color: AppColors.primary, width: 1.3),
    ),
  ),
  filledButtonTheme: FilledButtonThemeData(
    style: FilledButton.styleFrom(
      minimumSize: const Size(0, 44),
      elevation: 0,
      textStyle: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
    ),
  ),
  outlinedButtonTheme: OutlinedButtonThemeData(
    style: OutlinedButton.styleFrom(
      minimumSize: const Size(0, 42),
      side: const BorderSide(color: AppColors.line),
      foregroundColor: AppColors.ink,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
    ),
  ),
  drawerTheme: const DrawerThemeData(
    backgroundColor: AppColors.surface,
    width: 280,
    elevation: 0,
  ),
  dividerTheme: const DividerThemeData(
    color: AppColors.line,
    thickness: 1,
    space: 24,
  ),
  listTileTheme: const ListTileThemeData(
    iconColor: AppColors.muted,
    selectedColor: AppColors.primary,
    dense: true,
    minLeadingWidth: 24,
  ),
  dialogTheme: DialogThemeData(
    backgroundColor: AppColors.surface,
    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
  ),
  bottomSheetTheme: const BottomSheetThemeData(
    backgroundColor: AppColors.background,
    surfaceTintColor: Colors.transparent,
  ),
  progressIndicatorTheme: const ProgressIndicatorThemeData(
    color: AppColors.primary,
    linearTrackColor: AppColors.soft,
  ),
);
