from uuid import uuid4
from time import time
from collections import OrderedDict

from rdflib import RDF, Literal, URIRef
from sparqlquery import Select, v, union, optional, func

from jsongraph.vocab import ID, PRED


class Query(object):
    """ A query against a fully constructed JSON graph. The query language is
    based on Freebase's Metaweb Query Language, a JSON-based query-by-example
    method of interrogating graphs. """

    def __init__(self, context, parent, node):
        self.context = context
        self.parent = parent
        self.node = node
        self._results = []
        if node.name is None:
            self.id = 'root'
        else:
            prefix = '_any' if node.name == '*' else node.name
            self.id = '%s_%s' % (prefix, uuid4().hex[:10])
        self.var = v[self.id]

    @property
    def children(self):
        if not hasattr(self, '_children'):
            self._children = []
            for child_node in self.node.children:
                qb = Query(self.context, self, child_node)
                self._children.append(qb)
        return self._children

    @property
    def predicate(self):
        if self.node.name == '$schema':
            return RDF.type
        if self.node.specific_attribute:
            return PRED[self.node.name]
        return v['pred' + self.id]

    def project(self, q, parent=False):
        """ Figure out which attributes should be returned for the current
        level of the query. """
        q = q.project(self.var, append=True)
        if parent and self.parent:
            q = q.project(self.parent.var, append=True)
        for child in self.children:
            if child.node.blank and child.node.leaf:
                q = child.project(q)
        return q

    def filter(self, q, parents=None):
        """ Apply any filters to the query. """
        if self.node.leaf and self.node.filtered:
            q = q.where((self.parent.var,
                         self.predicate,
                         Literal(self.node.value)))
        elif self.parent is not None:
            q = q.where((self.parent.var, self.predicate, self.var))
            if parents is not None:
                parents = [URIRef(p) for p in parents]
                q = q.filter(self.parent.var.in_(*parents))
        for child in self.children:
            q = child.filter(q)
        return q

    def nested(self):
        """ A list of all sub-entities for which separate queries will
        be conducted. """
        for child in self.children:
            if child.node.nested:
                yield child

    def query(self, parents=None):
        """ Compose the query and generate SPARQL. """
        q = Select([])
        q = self.project(q, parent=True)
        q = self.filter(q, parents=parents)

        if self.parent is None:
            subq = Select([self.var])
            subq = self.filter(subq, parents=parents)
            subq = subq.offset(self.node.offset)
            subq = subq.limit(self.node.limit)
            subq = subq.distinct()
            q = q.where(subq)

        print 'QUERY', q.compile()
        return q

    def execute(self, parents=None):
        """ Run the data query and construct entities from it's results. """
        results = OrderedDict()
        for row in self.query(parents=parents).execute(self.context.graph):
            data = {k: v.toPython() for (k, v) in row.asdict().items()}
            id = data.get(self.id)
            if id not in results:
                results[id] = {}
                if self.parent is not None:
                    results[id]['$parent'] = data.get(self.parent.id)

            for child in self.children:
                if child.id in data:
                    name = child.node.name
                    value = data.get(child.id)
                    if child.node.many:
                        if name not in results[id]:
                            results[id][name] = [value]
                        else:
                            results[id][name].append(value)
                    else:
                        results[id][name] = value
        return results

    def collect(self, parents=None):
        """ Given re-constructed entities, conduct queries for child
        entities and merge them into the current level's object graph. """
        results = self.execute(parents=parents)
        ids = results.keys()
        for child in self.nested():
            name = child.node.name
            for child_data in child.collect(parents=ids).values():
                parent_id = child_data.pop('$parent', None)
                if child.node.many:
                    if name not in results[parent_id]:
                        results[parent_id][name] = []
                    results[parent_id][name].append(child_data)
                else:
                    results[parent_id][name] = child_data
        return results

    def run(self):
        results = []
        for result in self.collect().values():
            if not self.node.many:
                return result
            results.append(result)
        return results

    def results(self):
        t = time()
        result = self.run()
        return {
            'status': 'ok',
            'query': self.node.to_dict(),
            'result': result,
            'time': (time() - t) * 1000
        }
