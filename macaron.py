# -*- coding: utf-8 -*-
"""
Macaron is a very simple object-relational(O/R) mapper for SQLite3 in small applications.

:Author:
    Nobuo Okazaki

:License:
    MIT
"""
__author__ = "Nobuo Okazaki"
__version__ = "0.1.dev"
__license__ = "MIT"

import sqlite3
import re

def macaronage(*args, **kw):
    """Let's macaronage process

    @type  dbname: string
    @param dbname: database file name of SQLite
    """
    if kw.has_key("dbfile"):
        conn = sqlite3.connect(kw["dbfile"])
    elif kw.has_key("conn"):
        conn = kw["conn"]
    if not conn: raise Exception("Can't create connection.")
    _m.connection["default"] = conn

def bake(*args, **kw):
    """Let's bake the Macaron!!

    Committing the database
    """
    _m.connection["default"].commit()

class Macaron(object):
    """Macaron controller class. Do not instance this class by user."""
    def __init__(self):
        self.connection = {}

class Fields(list):
    """Field collection"""
    def __init__(self):
        self._field_dict = {}

    def append(self, fld):
        super(Fields, self).append(fld)
        self._field_dict[fld.name] = fld

    def __getitem__(self, name): return self._field_dict[name]

class Field(object):
    """Field information class"""
    def __init__(self, row):
        """
        @type  row: tuple
        @param row: tuple got from 'PRAGMA table_info(table_name)'
        """
        self.cid, self.name, self.type, \
            self.not_null, self.default, self.is_primary_key = row
        if re.match(r"^BOOLEAN$", self.type, re.I):
            self.default = bool(re.match(r"^TRUE$", self.default, re.I))

class ClassProperty(property):
    """Using class property wrapper class"""
    def __get__(self, owner_obj, cls):
        return self.fget.__get__(owner_obj, cls)()

class TableMeta(object):
    """Table information class"""
    def __init__(self, conn, table_name):
        self.fields = Fields()
        self.primary_key = None
        self.conn = conn
        cur = conn.cursor()
        rows = cur.execute("PRAGMA table_info(%s)" % table_name).fetchall()
        for row in rows:
            fld = Field(row)
            self.fields.append(Field(row))
            if fld.is_primary_key: self.primary_key = fld

class ManyToOne(property):
    """Many to one relation ship definition class"""
    def __init__(self, fkey, ref, ref_key=None, reverse_name=None):
        self.fkey = fkey                    #: foreign key name ('many' side)
        self.ref = ref                      #: reference table ('one' side)
        self.ref_key = ref_key              #: reference key ('one' side)
        self.reverse_name = reverse_name    #: accessor name for one to many relation

    def __get__(self, owner, cls):
        ref = self.ref._table_name
        sql = "SELECT %s.* FROM %s LEFT JOIN %s ON %s = %s.%s WHERE %s.%s = ?" \
            % (ref, cls._table_name, ref, self.fkey, ref, self.ref_key, \
               cls._table_name, cls._meta.primary_key.name)
        cur = cls._meta.conn.cursor()
        cur = cur.execute(sql, [owner.get_id()])
        row = cur.fetchone()
        if cur.fetchone(): raise ValueError()
        return self.ref._factory(cur, row)

    def set_reverse(self, rev_cls):
        """Setting up one to many definition method
        This method will be called in MetaModel#__init__.
        To inform the model class to ManyToOne and _ManyToOne_Rev classes.

        @type  rev_cls: class
        @param rev_cls: 'many' side class
        """
        self.reverse_name = self.reverse_name or "%s_set" % rev_cls.__name__.lower()
        setattr(self.ref, self.reverse_name, _ManyToOne_Rev(self.ref, self.ref_key, rev_cls, self.fkey))

class _ManyToOne_Rev(property):
    """The reverse of many to one relationship."""
    def __init__(self, ref, ref_key, rev, rev_fkey):
        self.ref = ref
        self.ref_key = ref_key
        self.rev = rev
        self.rev_fkey = rev_fkey

    def __get__(self, owner, cls):
        self.ref_key = self.ref_key or self.ref._meta.primary_key.name
        return self.rev.select("%s = ?" % self.rev_fkey, [getattr(owner, self.ref_key)])

class MetaModel(type):
    """Meta class for Model class"""
    def __new__(cls, name, bases, dict):
        if not dict.has_key("_table_name"):
            raise Exception("'%s._table_name' is not set." % name)
        return type.__new__(cls, name, bases, dict)

    def __init__(instance, name, bases, dict):
        for k in dict.keys():
            if isinstance(dict[k], ManyToOne):
                dict[k].set_reverse(instance)

class Model(object):
    """Base model class

    Models inherit the class.
    """
    __metaclass__ = MetaModel
    _table_name = None  #: Database table name
    _table_meta = None  #: Table information

    @classmethod
    def _get_meta(cls):
        if not cls._table_meta:
            cls._table_meta = TableMeta(_m.connection["default"], cls._table_name)
        return cls._table_meta
    _meta = ClassProperty(_get_meta)

    def __init__(self, **kw):
        cls = self.__class__
        if not cls._meta:
            cls._meta = TableMeta(_m.connection["default"], cls._table_name)
        for fld in cls._meta.fields: setattr(self, fld.name, fld.default)
        for k in kw.keys():
            if not hasattr(self, k): ValueError("Invalid column name '%s'." % k)
            setattr(self, k, kw[k])

    @classmethod
    def _factory(cls, cur, row):
        h = dict([[d[0], row[i]] for i, d in enumerate(cur.description)])
        return cls(**h)

    @classmethod
    def get(cls, id):
        return cls.select_one("%s = ?" % (cls._meta.primary_key.name), [id])

    @classmethod
    def select_one(cls, q, values):
        m = cls.select(q, values)
        try: obj = m.next()
        except StopIteration: raise cls.DoesNotFound()
        try: m.next()
        except StopIteration: return obj
        raise ValueError("Returns more rows.")

    @classmethod
    def select(cls, q, values):
        sql = "SELECT * FROM %s WHERE %s" % (cls._table_name, q)
        return cls._select(sql, values)

    @classmethod
    def _select(cls, sqlstr, values):
        def _(c):
            for row in c: yield cls._factory(c, row)
        return _(cls._meta.conn.cursor().execute(sqlstr, values))

    @classmethod
    def create(cls, **kw):
        names = []
        obj = cls(**kw)
        for fld in cls._meta.fields:
            if fld.is_primary_key and not getattr(obj, fld.name): continue
            names.append(fld.name)
        obj.before_create()
        obj.before_save()
        values = [getattr(obj, n) for n in names]
        holder = ", ".join(["?"] * len(names))
        sql = "INSERT INTO %s (%s) VALUES (%s)" % (cls._table_name, ", ".join(names), holder)
        cur = cls._meta.conn.cursor().execute(sql, values)
        newobj = cls.get(cur.lastrowid)
        for fld in cls._meta.fields: setattr(obj, fld.name, getattr(newobj, fld.name))

    def save(self):
        cls = self.__class__
        names = []
        for fld in cls._meta.fields:
            if fld.is_primary_key: continue
            names.append(fld.name)
        holder = ", ".join(["%s = ?" % n for n in names])
        self.before_save()
        values = [getattr(self, n) for n in names]
        sql = "UPDATE %s SET %s WHERE %s = ?" % (cls._table_name, holder, cls._meta.primary_key.name)
        cls._meta.conn.cursor().execute(sql, values + [self.get_id()])

    def delete(self):
        cls = self.__class__
        sql = "DELETE FROM %s WHERE %s = ?" % (cls._table_name, cls._meta.primary_key.name)
        cls._meta.conn.cursor().execute(sql, [self.get_id()])

    def get_id(self):
        return getattr(self, self.__class__._meta.primary_key.name)

    def before_create(self): pass
    def before_save(self): pass

    def __repr__(self):
        return "%s %s" % (self.__class__.__name__, self.get_id())

# This is a module global variable '_m' having Macaron object.
_m = Macaron()