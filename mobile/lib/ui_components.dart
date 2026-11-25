import 'package:flutter/material.dart';

import 'ui_theme.dart';

class ModuleSection {
  const ModuleSection({
    required this.title,
    required this.description,
    required this.child,
  });
  final String title, description;
  final Widget child;
}

/// Keep every form mounted, but give only one group layout, focus and semantics.
/// IndexedStack would reserve the height of the longest form on every step.
class ModuleSections extends StatefulWidget {
  const ModuleSections({
    super.key,
    required this.sections,
    this.enabled = true,
    this.overviewLabel = '查看全部分组',
    this.previousLabel = '上一组',
    this.nextLabel = '下一组',
  });
  final List<ModuleSection> sections;
  final bool enabled;
  final String overviewLabel, previousLabel, nextLabel;

  @override
  State<ModuleSections> createState() => ModuleSectionsState();
}

class ModuleSectionsState extends State<ModuleSections> {
  String? activeTitle;

  void open(int? index) {
    if (!mounted) return;
    FocusManager.instance.primaryFocus?.unfocus();
    setState(
      () => activeTitle = index == null ? null : widget.sections[index].title,
    );
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        Scrollable.ensureVisible(
          context,
          alignment: 0,
          duration: const Duration(milliseconds: 180),
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final found = widget.sections.indexWhere((s) => s.title == activeTitle);
    final int? index = found < 0 ? null : found;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (index == null)
          Card(
            child: Column(
              children: [
                for (var i = 0; i < widget.sections.length; i++) ...[
                  if (i > 0) const Divider(height: 1),
                  ListTile(
                    contentPadding: const EdgeInsets.symmetric(
                      horizontal: 16,
                      vertical: 8,
                    ),
                    title: Text(widget.sections[i].title),
                    subtitle: Text(widget.sections[i].description),
                    trailing: const Icon(Icons.chevron_right, size: 20),
                    onTap: widget.enabled ? () => open(i) : null,
                  ),
                ],
              ],
            ),
          )
        else ...[
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: widget.enabled ? () => open(null) : null,
              icon: const Icon(Icons.arrow_back, size: 18),
              label: Text(widget.overviewLabel),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            '${index + 1} / ${widget.sections.length} · ${widget.sections[index].title}',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 8),
          Text(
            widget.sections[index].description,
            style: const TextStyle(color: AppColors.muted),
          ),
          const SizedBox(height: 16),
        ],
        for (var i = 0; i < widget.sections.length; i++)
          Offstage(
            key: ValueKey(widget.sections[i].title),
            offstage: index != i,
            child: ExcludeFocus(
              excluding: index != i,
              child: TickerMode(
                enabled: index == i,
                child: widget.sections[i].child,
              ),
            ),
          ),
        if (index != null) ...[
          const SizedBox(height: 16),
          Wrap(
            spacing: 12,
            runSpacing: 8,
            children: [
              if (index > 0)
                OutlinedButton(
                  onPressed: widget.enabled ? () => open(index - 1) : null,
                  child: Text(widget.previousLabel),
                ),
              if (index + 1 < widget.sections.length)
                OutlinedButton(
                  onPressed: widget.enabled ? () => open(index + 1) : null,
                  child: Text(widget.nextLabel),
                ),
            ],
          ),
        ],
        const SizedBox(height: 16),
      ],
    );
  }
}

/// One frame for scrollable business pages; widths are local to the canvas.
class AppContent extends StatelessWidget {
  const AppContent({super.key, required this.child, this.maxWidth = 1040});
  final Widget child;
  final double maxWidth;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, box) => SingleChildScrollView(
      padding: EdgeInsets.all(box.maxWidth < 640 ? 16 : 32),
      child: Center(
        child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: maxWidth),
          child: SizedBox(width: double.infinity, child: child),
        ),
      ),
    ),
  );
}

class PageIntro extends StatelessWidget {
  const PageIntro({
    super.key,
    required this.title,
    required this.description,
    this.action,
  });
  final String title, description;
  final Widget? action;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 24),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Semantics(
          header: true,
          child: Text(title, style: Theme.of(context).textTheme.headlineSmall),
        ),
        const SizedBox(height: 8),
        Text(description, style: const TextStyle(color: AppColors.muted)),
        if (action != null) ...[const SizedBox(height: 16), action!],
      ],
    ),
  );
}

/// Two equally sized columns, or one column when either would be under 360px.
/// Width arithmetic: 2 * ((available - 16) / 2) + 16 = available.
class AdaptiveColumns extends StatelessWidget {
  const AdaptiveColumns({super.key, required this.first, required this.second});
  final Widget first, second;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, box) {
      final width = box.maxWidth < 736 ? box.maxWidth : (box.maxWidth - 16) / 2;
      // Keep the same child elements across breakpoints, including unsaved forms.
      return Wrap(
        spacing: 16,
        children: [
          SizedBox(width: width, child: first),
          SizedBox(width: width, child: second),
        ],
      );
    },
  );
}

class AdaptiveFields extends StatelessWidget {
  const AdaptiveFields({
    super.key,
    required this.children,
    this.minWidth = 240,
    this.maxColumns = 2,
  });
  final List<Widget> children;
  final double minWidth;
  final int maxColumns;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, box) {
      final columns = ((box.maxWidth + 16) / (minWidth + 16)).floor().clamp(
        1,
        maxColumns,
      );
      final width = (box.maxWidth - (columns - 1) * 16) / columns;
      return Wrap(
        spacing: 16,
        runSpacing: 16,
        children: [
          for (final child in children) SizedBox(width: width, child: child),
        ],
      );
    },
  );
}
