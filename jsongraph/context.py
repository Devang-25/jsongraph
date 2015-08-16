from rdflib import Graph, URIRef

from jsongraph.converter import Converter
from jsongraph.vocab import BNode, META
from jsongraph.provenance import Provenance


class Context(object):

    def __init__(self, parent, identifier=None, prov=None):
        self.parent = parent
        if identifier is None:
            identifier = BNode()
        self.identifier = URIRef(identifier)
        self.prov = Provenance(self, prov)

    @property
    def graph(self):
        if not hasattr(self, '_graph') or self._graph is None:
            self._graph = Graph(identifier=self.identifier)
        return self._graph

    def add(self, schema, data):
        """ Stage ``data`` as a set of statements, based on the given
        ``schema`` definition. """
        schema = self.parent.get_schema(schema)
        uri = Converter.import_data(self.parent.resolver, self.graph,
                                    data, schema)
        self.save()
        return uri

    def save(self):
        """ Transfer the statements in this context over to the main store. """
        self.prov.generate()
        query = """
            DELETE WHERE { GRAPH %s { %s ?pred ?val } } ;
            INSERT DATA { GRAPH %s { %s } }
        """
        query = query % (self.identifier.n3(),
                         self.identifier.n3(),
                         self.identifier.n3(),
                         self.graph.serialize(format='nt'))
        print query
        self.parent.graph.update(query)
        self.flush()
        self._create = False

    def delete(self):
        """ Delete all statements matching the current context identifier
        from the main store. """
        query = 'CLEAR SILENT GRAPH %s ;' % self.identifier.n3()
        self.parent.graph.update(query)
        self.flush()

    def flush(self):
        """ Clear all the pending statements in the local context, without
        transferring them to the main store. """
        self._graph = None

    def __str__(self):
        return self.identifier

    def __repr__(self):
        return '<Context("%s")>' % self.identifier