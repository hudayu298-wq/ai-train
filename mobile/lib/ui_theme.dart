import 'package:flutter/material.dart';

abstract final class AppColors {
  static const background = Color(0xfff4f5f7);
  static const surface = Colors.white;
  static const ink = Color(0xff20242a);
  static const muted = Color(0xff606773);
  static const line = Color(0xffe4e6ea);
  static const primary = Color(0xff2462b8);
  static const soft = Color(0xfff0f1f3);
  static const selected = Color(0xffe6e8ec);
}

ThemeData buildAppTheme() => ThemeData(
  useMaterial3: true,
  fontFamily: 'LianbanSans',
  colorScheme: ColorScheme.fromSeed(seedColor: AppColors.primary).copyWith(
    primary: AppColors.primary,
    onPrimary: Colors.white,
    secondary: AppColors.ink,
    tertiary: AppColors.primary,
    surface: AppColors.surface,
    onSurface: AppColors.ink,
    outline: const Color(0xffccd2dd),
    outlineVariant: AppColors.line,
  ),
  scaffoldBackgroundColor: AppColors.background,
  textTheme: const TextTheme(
    headlineMedium: TextStyle(
      fontSize: 28,
      height: 1.25,
      fontWeight: FontWeight.w600,
      color: AppColors.ink,
      letterSpacing: -.6,
    ),
    headlineSmall: TextStyle(
      fontSize: 24,
      height: 1.3,
      fontWeight: FontWeight.w600,
      color: AppColors.ink,
      letterSpacing: -.4,
    ),
    titleLarge: TextStyle(
      fontSize: 18,
      height: 1.4,
      fontWeight: FontWeight.w600,
      color: AppColors.ink,
    ),
    titleMedium: TextStyle(
      fontSize: 16,
      height: 1.4,
      fontWeight: FontWeight.w600,
      color: AppColors.ink,
    ),
    bodyLarge: TextStyle(fontSize: 16, height: 1.55, color: AppColors.ink),
    bodyMedium: TextStyle(fontSize: 14, height: 1.55, color: AppColors.ink),
    bodySmall: TextStyle(fontSize: 12, height: 1.5, color: AppColors.muted),
    labelLarge: TextStyle(fontSize: 14, fontWeight: FontWeight.w500),
  ),
  appBarTheme: const AppBarTheme(
    backgroundColor: AppColors.surface,
    foregroundColor: AppColors.ink,
    elevation: 0,
    scrolledUnderElevation: 0,
    centerTitle: false,
    titleTextStyle: TextStyle(
      fontFamily: 'LianbanSans',
      fontSize: 18,
      fontWeight: FontWeight.w600,
      color: AppColors.ink,
    ),
    shape: Border(bottom: BorderSide(color: AppColors.line)),
  ),
  cardTheme: CardThemeData(
    color: AppColors.surface,
    elevation: 0,
    margin: const EdgeInsets.only(bottom: 16),
    shape: RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(8),
      side: const BorderSide(color: AppColors.line),
    ),
  ),
  inputDecorationTheme: InputDecorationTheme(
    filled: true,
    fillColor: AppColors.surface,
    floatingLabelBehavior: FloatingLabelBehavior.always,
    contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
    labelStyle: const TextStyle(fontSize: 14, color: AppColors.muted),
    hintStyle: const TextStyle(fontSize: 14, color: AppColors.muted),
    border: OutlineInputBorder(
      borderRadius: BorderRadius.circular(6),
      borderSide: const BorderSide(color: AppColors.line),
    ),
    enabledBorder: OutlineInputBorder(
      borderRadius: BorderRadius.circular(6),
      borderSide: const BorderSide(color: AppColors.line),
    ),
    focusedBorder: OutlineInputBorder(
      borderRadius: BorderRadius.circular(6),
      borderSide: const BorderSide(color: AppColors.primary, width: 1.3),
    ),
  ),
  filledButtonTheme: FilledButtonThemeData(
    style: FilledButton.styleFrom(
      backgroundColor: AppColors.ink,
      foregroundColor: Colors.white,
      minimumSize: const Size(0, 44),
      elevation: 0,
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
      textStyle: const TextStyle(
        fontFamily: 'LianbanSans',
        fontSize: 14,
        fontWeight: FontWeight.w500,
      ),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
    ),
  ),
  outlinedButtonTheme: OutlinedButtonThemeData(
    style: OutlinedButton.styleFrom(
      minimumSize: const Size(0, 44),
      side: const BorderSide(color: AppColors.line),
      foregroundColor: AppColors.ink,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
    ),
  ),
  drawerTheme: const DrawerThemeData(
    backgroundColor: AppColors.background,
    width: 288,
    elevation: 0,
  ),
  dividerTheme: const DividerThemeData(
    color: AppColors.line,
    thickness: 1,
    space: 24,
  ),
  listTileTheme: const ListTileThemeData(
    iconColor: AppColors.muted,
    selectedColor: AppColors.ink,
    selectedTileColor: AppColors.selected,
    dense: false,
    minTileHeight: 48,
    minLeadingWidth: 24,
  ),
  textButtonTheme: TextButtonThemeData(
    style: TextButton.styleFrom(
      foregroundColor: AppColors.ink,
      minimumSize: const Size(44, 44),
    ),
  ),
  chipTheme: ChipThemeData(
    backgroundColor: AppColors.soft,
    selectedColor: AppColors.selected,
    secondarySelectedColor: AppColors.selected,
    checkmarkColor: AppColors.ink,
    side: BorderSide.none,
    labelStyle: const TextStyle(
      fontFamily: 'LianbanSans',
      fontSize: 12,
      color: AppColors.muted,
    ),
    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
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
