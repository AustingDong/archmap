export type Locale = 'en' | 'cn'

const dict: Record<Locale, Record<string, string>> = {
  en: {
    'app.title': 'ArchMap',
    'app.subtitle': 'Understand your project, progressively',
    'app.enter_path': 'Enter project path...',
    'app.load': 'Load',
    'app.loading': 'Loading...',
    'app.no_project': 'Enter a project path to get started.',
    'app.theme_light': 'Light',
    'app.theme_dark': 'Dark',

    'tree.empty_title': 'No tree yet',
    'tree.empty_desc': 'Start by naming this project and what it does.',
    'tree.project_name': 'Project name',
    'tree.one_line': 'What does it do?',
    'tree.create_root': 'Create',
    'tree.reset': 'Reset tree',
    'tree.reset_confirm': 'Reset the tree? All nodes will be removed.',
    'tree.files': 'files',

    'node.add_child': 'Add child',
    'node.attach': 'Attach files',
    'node.remove': 'Remove',
    'node.remove_confirm': 'Remove "{name}" and all its children?',
    'node.edit': 'Edit',
    'node.save': 'Save',
    'node.cancel': 'Cancel',
    'node.purpose_name': 'Purpose name',
    'node.what_it_does': 'What it does',
    'node.description': 'Description',
    'node.your_notes': 'Your notes...',
    'node.approve': 'Approve',
    'node.reject': 'Reject',
    'node.approve_del': 'Approve deletion',
    'node.unmapped_files': 'Unmapped files',
    'node.all_mapped': 'All files mapped.',

    'status.confirmed': 'Confirmed',

    'status.proposed': 'Proposed — approve or reject',
    'status.removing': 'Proposed for removal',

    'task.title': 'Tasks',
    'task.placeholder': 'Describe the next task...',
    'task.add': 'Add',
    'task.done': 'Done',
    'task.reject': 'Reject',
    'task.empty': 'No tasks yet. Create one to scope agent work.',
    'task.active': 'Active',
    'task.queued': 'Queued',
    'task.completed': 'Completed',
    'task.rejected': 'Rejected',

    'toast.approved': 'Approved: {name}',
    'toast.rejected': 'Rejected: {name}',
    'toast.tree_reset': 'Tree reset',

    'stats.total': 'Total',
    'stats.confirmed': 'Confirmed',

    'stats.proposed': 'Proposed',

    'tree.expand_all': 'Expand all',
    'tree.collapse_all': 'Collapse all',
    'tree.search_placeholder': 'Filter nodes by name...',

    'task.active_banner': 'Active task',
    'task.target_node': 'Target node',

    'hover.status': 'Status',
    'hover.files': 'Files',
    'hover.description': 'Description',
    'hover.created': 'Created',

    'progress.title': 'Progress',
    'progress.confirmed_of_total': '{confirmed} of {total} confirmed',
  },
  cn: {
    'app.title': 'ArchMap',
    'app.subtitle': '\u6e10\u8fdb\u5f0f\u7406\u89e3\u4f60\u7684\u9879\u76ee',
    'app.enter_path': '\u8f93\u5165\u9879\u76ee\u8def\u5f84...',
    'app.load': '\u52a0\u8f7d',
    'app.loading': '\u52a0\u8f7d\u4e2d...',
    'app.no_project': '\u8f93\u5165\u9879\u76ee\u8def\u5f84\u5f00\u59cb\u4f7f\u7528\u3002',
    'app.theme_light': '\u6d45\u8272',
    'app.theme_dark': '\u6df1\u8272',

    'tree.empty_title': '\u8fd8\u6ca1\u6709\u6811',
    'tree.empty_desc': '\u5148\u547d\u540d\u8fd9\u4e2a\u9879\u76ee\uff0c\u5e76\u63cf\u8ff0\u5b83\u505a\u4ec0\u4e48\u3002',
    'tree.project_name': '\u9879\u76ee\u540d\u79f0',
    'tree.one_line': '\u5b83\u505a\u4ec0\u4e48\uff1f',
    'tree.create_root': '\u521b\u5efa',
    'tree.reset': '\u91cd\u7f6e\u6811',
    'tree.reset_confirm': '\u786e\u8ba4\u91cd\u7f6e\uff1f\u6240\u6709\u8282\u70b9\u5c06\u88ab\u5220\u9664\u3002',
    'tree.files': '\u6587\u4ef6',

    'node.add_child': '\u6dfb\u52a0\u5b50\u8282\u70b9',
    'node.attach': '\u5173\u8054\u6587\u4ef6',
    'node.remove': '\u5220\u9664',
    'node.remove_confirm': '\u5220\u9664\u201c{name}\u201d\u53ca\u5176\u6240\u6709\u5b50\u8282\u70b9\uff1f',
    'node.edit': '\u7f16\u8f91',
    'node.save': '\u4fdd\u5b58',
    'node.cancel': '\u53d6\u6d88',
    'node.purpose_name': '\u529f\u80fd\u540d\u79f0',
    'node.what_it_does': '\u5b83\u505a\u4ec0\u4e48',
    'node.description': '\u63cf\u8ff0',
    'node.your_notes': '\u4f60\u7684\u7b14\u8bb0...',
    'node.approve': '\u901a\u8fc7',
    'node.reject': '\u62d2\u7edd',
    'node.approve_del': '\u786e\u8ba4\u5220\u9664',
    'node.unmapped_files': '\u672a\u5173\u8054\u6587\u4ef6',
    'node.all_mapped': '\u6240\u6709\u6587\u4ef6\u5df2\u5173\u8054\u3002',

    'status.confirmed': '\u5df2\u786e\u8ba4',

    'status.proposed': '\u5f85\u5ba1\u6838 \u2014 \u901a\u8fc7\u6216\u62d2\u7edd',
    'status.removing': '\u5efa\u8bae\u5220\u9664',

    'task.title': '\u4efb\u52a1',
    'task.placeholder': '\u63cf\u8ff0\u4e0b\u4e00\u4e2a\u4efb\u52a1...',
    'task.add': '\u6dfb\u52a0',
    'task.done': '\u5b8c\u6210',
    'task.reject': '\u62d2\u7edd',
    'task.empty': '\u8fd8\u6ca1\u6709\u4efb\u52a1\u3002\u521b\u5efa\u4e00\u4e2a\u6765\u5f15\u5bfc\u4ee3\u7406\u5de5\u4f5c\u3002',
    'task.active': '\u8fdb\u884c\u4e2d',
    'task.queued': '\u6392\u961f\u4e2d',
    'task.completed': '\u5df2\u5b8c\u6210',
    'task.rejected': '\u5df2\u62d2\u7edd',

    'toast.approved': '\u5df2\u901a\u8fc7\uff1a{name}',
    'toast.rejected': '\u5df2\u62d2\u7edd\uff1a{name}',
    'toast.tree_reset': '\u6811\u5df2\u91cd\u7f6e',

    'stats.total': '\u603b\u8ba1',
    'stats.confirmed': '\u5df2\u786e\u8ba4',

    'stats.proposed': '\u5f85\u5ba1\u6838',

    'tree.expand_all': '\u5168\u90e8\u5c55\u5f00',
    'tree.collapse_all': '\u5168\u90e8\u6536\u8d77',
    'tree.search_placeholder': '\u6309\u540d\u79f0\u7b5b\u9009\u8282\u70b9...',

    'task.active_banner': '\u5f53\u524d\u4efb\u52a1',
    'task.target_node': '\u76ee\u6807\u8282\u70b9',

    'hover.status': '\u72b6\u6001',
    'hover.files': '\u6587\u4ef6',
    'hover.description': '\u63cf\u8ff0',
    'hover.created': '\u521b\u5efa\u65f6\u95f4',

    'progress.title': '\u8fdb\u5ea6',
    'progress.confirmed_of_total': '{confirmed} / {total} \u5df2\u786e\u8ba4',
  },
}

export function t(locale: Locale, key: string, params?: Record<string, string>): string {
  let s = dict[locale]?.[key] ?? dict.en[key] ?? key
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      s = s.replace(`{${k}}`, v)
    }
  }
  return s
}
