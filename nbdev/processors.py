# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/api/10_processors.ipynb.

# %% auto 0
__all__ = ['populate_language', 'insert_warning', 'cell_lang', 'add_show_docs', 'fdiv', 'boxify', 'mv_exports', 'add_links',
           'add_fold', 'strip_ansi', 'strip_hidden_metadata', 'hide_', 'hide_line', 'filter_stream_', 'clean_magics',
           'rm_header_dash', 'rm_export', 'clean_show_doc', 'exec_show_docs', 'FilterDefaults']

# %% ../nbs/api/10_processors.ipynb 2
import ast
import importlib

from .config import *
from .imports import *
from .process import *
from .showdoc import *
from .doclinks import *
from .frontmatter import *
from .frontmatter import _fm2dict

from execnb.nbio import *
from execnb.shell import *
from fastcore.imports import *
from fastcore.xtras import *
import sys,yaml

# %% ../nbs/api/10_processors.ipynb 7
_langs = 'bash|html|javascript|js|latex|markdown|perl|ruby|sh|svg'
_lang_pattern = re.compile(rf'^\s*%%\s*({_langs})\s*$', flags=re.MULTILINE)

class populate_language(Processor):
    "Set cell language based on NB metadata and magics"
    def begin(self): self.language = nb_lang(self.nb)
    def cell(self, cell):
        if cell.cell_type != 'code': return
        lang = _lang_pattern.findall(cell.source)
        if lang: cell.metadata.language = lang[0]
        else: cell.metadata.language = self.language

# %% ../nbs/api/10_processors.ipynb 9
class insert_warning(Processor):
    "Insert Autogenerated Warning Into Notebook after the first cell."
    content = "<!-- WARNING: THIS FILE WAS AUTOGENERATED! DO NOT EDIT! -->"
    def begin(self): self.nb.cells.insert(1, mk_cell(self.content, 'markdown'))

# %% ../nbs/api/10_processors.ipynb 13
_def_types = (ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)
def _def_names(cell, shown):
    cellp = cell.parsed_()
    return [showdoc_nm(o) for o in concat(cellp)
            if isinstance(o,_def_types) and o.name not in shown and (o.name[0]!='_' or o.name[:2]=='__')] if cellp else []

def _get_nm(tree):
    i = tree.value.args[0]
    if hasattr(i, 'id'): val = i.id
    else: val = try_attrs(i.value, 'id', 'func', 'attr')
    return f'{val}.{i.attr}' if isinstance(i, ast.Attribute) else i.id

# %% ../nbs/api/10_processors.ipynb 14
def _show_docs(trees):
    return [t for t in trees if isinstance(t,ast.Expr) and nested_attr(t, 'value.func.id')=='show_doc']

def cell_lang(cell): return nested_attr(cell, 'metadata.language', 'python')

def _want_doc(c):
    d = c.directives_
    show_d = set(['export', 'exports', 'exec_doc']).intersection(d)
    return c.source and c.cell_type=='code' and show_d and 'hide' not in d and d.get('include:') != ['false']

class add_show_docs(Processor):
    "Add show_doc cells after exported cells, unless they are already documented"
    def begin(self):
        nb = self.nb
        exports = L(cell for cell in nb.cells if _want_doc(cell))
        trees = L(nb.cells).map(NbCell.parsed_).concat()
        shown_docs = {_get_nm(t) for t in _show_docs(trees)}
        for cell in reversed(exports):
            if cell_lang(cell) != 'python':  raise ValueError(f"{cell.metadata.language} can't export:\n{cell.source}")
            nms = _def_names(cell, shown_docs)
            for nm in nms:
                new_cell = mk_cell(f'show_doc({nm})')
                new_cell.has_sd = True
                nb.cells.insert(cell.idx_+1, new_cell)
        nb.has_docs_ = shown_docs or exports

# %% ../nbs/api/10_processors.ipynb 17
def fdiv(attrs=''):
    "Create a fenced div markdown cell in quarto"
    if attrs: attrs = ' {'+attrs+'}'
    return mk_cell(':::'+attrs, cell_type='markdown')

# %% ../nbs/api/10_processors.ipynb 19
def boxify(cells):
    "Add a box around `cells`"
    if not isinstance(cells, list): cells = [cells]
    res = [fdiv('.py-2 .px-3 .mb-4 fig-align="center" .border .rounded .shadow-sm')]
    return res+cells+[fdiv()]

# %% ../nbs/api/10_processors.ipynb 20
class mv_exports(Processor):
    "Move `exports` cells to after the `show_doc`"
    def begin(self):
        cells = self.nb.cells
        exports = L(c for c in cells if c.cell_type=='code' and 'exports' in c.directives_)
        for cell in reversed(exports):
            idx = cell.idx_
            if getattr(cells[idx+1], 'has_sd', 0):
                doccell = cells.pop(idx+1)
                srccell = cells.pop(idx)
                cells[idx:idx] = boxify([doccell,srccell])

# %% ../nbs/api/10_processors.ipynb 21
_re_defaultexp = re.compile(r'^\s*#\|\s*default_exp\s+(\S+)', flags=re.MULTILINE)

def _default_exp(nb):
    "get the default_exp from a notebook"
    code_src = L(nb.cells).filter(lambda x: x.cell_type == 'code').attrgot('source')
    default_exp = first(code_src.filter().map(_re_defaultexp.search).filter())
    return default_exp.group(1) if default_exp else None

# %% ../nbs/api/10_processors.ipynb 23
def add_links(cell):
    "Add links to markdown cells"
    nl = NbdevLookup()
    if cell.cell_type == 'markdown': cell.source = nl.linkify(cell.source)
    for o in cell.get('outputs', []):
        if hasattr(o, 'data') and hasattr(o['data'], 'text/markdown'):
            o.data['text/markdown'] = [nl.link_line(s) for s in o.data['text/markdown']]

# %% ../nbs/api/10_processors.ipynb 25
def add_fold(cell):
    "Add `code-fold` to `exports` cells"
    if cell.cell_type != 'code' or 'exports' not in cell.directives_: return
    cell.source = f'#| code-fold: show\n#| code-summary: "Exported source"\n{cell.source}'

# %% ../nbs/api/10_processors.ipynb 28
_re_ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

def strip_ansi(cell):
    "Strip Ansi Characters."
    for outp in cell.get('outputs', []):
        if outp.get('name')=='stdout': outp['text'] = [_re_ansi_escape.sub('', o) for o in outp.text]

# %% ../nbs/api/10_processors.ipynb 30
def strip_hidden_metadata(cell):
    '''Strips "hidden" metadata property from code cells so it doesn't interfere with docs rendering'''
    if cell.cell_type == 'code' and 'metadata' in cell: cell.metadata.pop('hidden',None)

# %% ../nbs/api/10_processors.ipynb 31
def hide_(cell):
    "Hide cell from output"
    del(cell['source'])

# %% ../nbs/api/10_processors.ipynb 33
def _re_hideline(lang=None): return re.compile(fr'{langs[lang]}\|\s*hide_line\s*$', re.MULTILINE)

def hide_line(cell):
    "Hide lines of code in code cells with the directive `hide_line` at the end of a line of code"
    lang = cell_lang(cell)
    if cell.cell_type == 'code' and _re_hideline(lang).search(cell.source):
        cell.source = '\n'.join([c for c in cell.source.splitlines() if not _re_hideline(lang).search(c)])

# %% ../nbs/api/10_processors.ipynb 36
def filter_stream_(cell, *words):
    "Remove output lines containing any of `words` in `cell` stream output"
    if not words: return
    for outp in cell.get('outputs', []):
        if outp.output_type == 'stream':
            outp['text'] = [l for l in outp.text if not re.search('|'.join(words), l)]

# %% ../nbs/api/10_processors.ipynb 38
_magics_pattern = re.compile(r'^\s*(%%|%).*', re.MULTILINE)

def clean_magics(cell):
    "A preprocessor to remove cell magic commands"
    if cell.cell_type == 'code': cell.source = _magics_pattern.sub('', cell.source).strip()

# %% ../nbs/api/10_processors.ipynb 40
_re_hdr_dash = re.compile(r'^#+\s+.*\s+-\s*$', re.MULTILINE)

def rm_header_dash(cell):
    "Remove headings that end with a dash -"
    if cell.source:
        src = cell.source.strip()
        if cell.cell_type == 'markdown' and src.startswith('#') and src.endswith(' -'): del(cell['source'])

# %% ../nbs/api/10_processors.ipynb 42
_hide_dirs = {'export','exporti', 'hide','default_exp'}

def rm_export(cell):
    "Remove cells that are exported or hidden"
    if cell.directives_ and (cell.directives_.keys() & _hide_dirs): del(cell['source'])

# %% ../nbs/api/10_processors.ipynb 44
_re_showdoc = re.compile(r'^show_doc', re.MULTILINE)
def _is_showdoc(cell): return cell['cell_type'] == 'code' and _re_showdoc.search(cell.source)
def _add_directives(cell, d):
    for k,v in d.items():
        if not re.findall(f'#\| *{k}:', cell.source): cell.source = f'#| {k}: {v}\n' + cell.source

def clean_show_doc(cell):
    "Remove ShowDoc input cells"
    if not _is_showdoc(cell): return
    _add_directives(cell, {'output':'asis','echo':'false'})

# %% ../nbs/api/10_processors.ipynb 45
def _ast_contains(trees, types):
    for tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, types): return True

def _do_eval(cell):
    if cell_lang(cell) != 'python': return
    if not cell.source or 'nbdev_export'+'()' in cell.source: return
    trees = cell.parsed_()
    if cell.cell_type != 'code' or not trees: return
    if cell.directives_.get('eval:', [''])[0].lower() == 'false': return

    _show_dirs = {'export','exports','exporti','exec_doc'}
    if cell.directives_.keys() & _show_dirs: return True
    if _ast_contains(trees, (ast.Import, ast.ImportFrom)):
        if _ast_contains(trees, (ast.Expr, ast.Assign)):
            warn(f'Found cells containing imports and other code. See FAQ.\n---\n{cell.source}\n---\n')
        return True
    if _show_docs(trees): return True

# %% ../nbs/api/10_processors.ipynb 46
class exec_show_docs(Processor):
    "Execute cells needed for `show_docs` output, including exported cells and imports"
    def begin(self):
        if nb_lang(self.nb) != 'python': return
        self.k = CaptureShell()
        self.k.run_cell('from nbdev.showdoc import show_doc')

    def __call__(self, cell):
        if not self.nb.has_docs_ or not hasattr(self, 'k'): return
        fm = getattr(self.nb, 'frontmatter_', {})
        if str2bool(fm.get('skip_showdoc', False)): return
        if _do_eval(cell): self.k.cell(cell)
        title = fm.get('title', '')
        if self.k.exc: 
            raise Exception(f"Error{' in notebook: '+title if title else ''} in cell {cell.idx_} :\n{cell.source}") from self.k.exc[1]

    def end(self):
        try: from ipywidgets import Widget
        except ImportError: pass
        else:
            mimetype = 'application/vnd.jupyter.widget-state+json'
            old = nested_idx(self.nb.metadata, 'widgets', mimetype) or {'state': {}}
            new = Widget.get_manager_state(drop_defaults=True)
            widgets = {**old, **new, 'state': {**old.get('state', {}), **new['state']}}
            self.nb.metadata['widgets'] = {mimetype: widgets}

# %% ../nbs/api/10_processors.ipynb 48
def _import_obj(s):
    mod_nm, obj_nm = s.split(':')
    mod = importlib.import_module(mod_nm)
    return getattr(mod, obj_nm)

# %% ../nbs/api/10_processors.ipynb 49
class FilterDefaults:
    "Override `FilterDefaults` to change which notebook processors are used"
    def xtra_procs(self):
        imps = get_config().get('procs', '').split()
        return [_import_obj(o) for o in imps]

    def base_procs(self):
        return [FrontmatterProc, populate_language, add_show_docs, insert_warning,
                strip_ansi, hide_line, filter_stream_, rm_header_dash,
                clean_show_doc, exec_show_docs, rm_export, clean_magics, hide_, add_links, add_fold, mv_exports, strip_hidden_metadata]

    def procs(self):
        "Processors for export"
        return self.base_procs() + self.xtra_procs()
    
    def nb_proc(self, nb):
        "Get an `NBProcessor` with these processors"
        return NBProcessor(nb=nb, procs=self.procs())
    
    def __call__(self, nb): return self.nb_proc(nb).process()
