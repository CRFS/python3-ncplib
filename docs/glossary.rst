Glossary
========

.. glossary::

    identifier
        A :class:`str` of ascii uppercase letters and numbers, at most 4 characters long, e.g. ``"DSPC"``.

    NCP
        Node Communication Protocol, a binary communication and control protocol, developed by `CRFS`_.

    NCP field
        Each :term:`NCP packet` contains zero or more fields. A field consists of a field *name*, which must be a valid :term:`identifier`, and zero or more :term:`NCP parameters <NCP parameter>`.

        :mod:`ncplib` represents each field in an incoming :term:`NCP packet` as a :class:`ncplib.Field` instance.

    NCP packet
        The basic unit of :term:`NCP` communication. A packet consists of a packet *type*, which must be a valid :term:`identifier`, and zero or more :term:`NCP fields <NCP field>`.

    NCP parameter
        Each :term:`NCP field` contains zero or more parameters. A parameter consists of a parameter *name*, which must be a valid :term:`identifier`, and a *value*, which must be one of the supported :doc:`value types <values>`.

        :mod:`ncplib` represents each parameter as a name/value mapping on a :class:`ncplib.Field` instance.


.. include:: /_include/links.rst
