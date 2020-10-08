from retrobiocat_web.mongo.models.biocatdb_models import Sequence, EnzymeType, UniRef50, SeqSimNet
from retrobiocat_web.analysis.all_by_all_blast import AllByAllBlaster
from flask import render_template, flash, redirect, url_for, request, jsonify, session, current_app
import mongoengine as db
import networkx as nx
import time
import json
from rq.registry import StartedJobRegistry
from pathlib import Path
import os
import pandas as pd
from bson.binary import Binary
from collections import Counter
import random
import numpy as np


class RndColGen(object):

    def __init__(self, pastel_factor=1, existing_colours=None):
        if existing_colours is None:
            self.existing_colours = []
        else:
            self.existing_colours = existing_colours

    @staticmethod
    def get_random_color(pastel_factor):
        return [(x+pastel_factor)/(1.0+pastel_factor) for x in [random.randint(0, 256) for i in [1,2,3]]]

    @staticmethod
    def colour_distance(c1,c2):
        return sum([abs(x[0]-x[1]) for x in zip(c1,c2)])

    def generate_new_colour(self, pastel_factor=0.9):
        max_distance = None
        best_color = None
        for i in range(0,100):
            colour = self.get_random_color(pastel_factor)
            if len(self.existing_colours) == 0:
                return colour
            best_distance = min([self.colour_distance(colour, c) for c in self.existing_colours])
            if not max_distance or best_distance > max_distance:
                max_distance = best_distance
                best_color = colour
        return best_color

    def average_colour(self, list_colours):
        new_colour = list(np.mean(list_colours, axis=0, dtype=int))
        self.existing_colours.append(new_colour)
        return new_colour

class SSN_Clusterer(object):

    def __init__(self, enzyme_type, ssn, cluster_min_nodes=8, initial_alignment_score=400, log_level=0):
        self.enzyme_type = enzyme_type
        self.enzyme_type_obj = EnzymeType.objects(enzyme_type=enzyme_type)[0]

        self.cluster_min_nodes = cluster_min_nodes
        self.initial_alignment_score = initial_alignment_score
        self.step = -5
        self.end_score = 0

        self.log_level = log_level

        self.ssn = ssn
        self.visualiser = SSN_Visualiser(enzyme_type, log_level=log_level)
        self.rndcolgen = RndColGen()
        self.space_per_node = 2

    def make_visualisations(self):
        clusters_dict, graphs_dict = self.make_cluster_dict()
        node_colours = self.get_node_colours(clusters_dict)

        vis_dict = {}
        for score, clusters in clusters_dict.items():
            self.log(f"Getting vis nodes at score {score}")
            vis_dict[score] = [[], []]
            num_clusters = len(clusters)
            rows = int(np.sqrt(num_clusters))
            center = [0, 0]
            v_move = 0
            for i, cluster in enumerate(clusters):
                move = self._cluster_box_move(cluster)
                center, v_move = self._move(i, center, v_move, move, rows)
                nodes, edges = self.get_cluster_visualisation(graphs_dict[score], cluster, center, node_colours)
                vis_dict[score][0] += nodes
                vis_dict[score][1] += edges
                center, v_move = self._move(i, center, v_move, move, rows)

        return vis_dict

    def get_cluster_visualisation(self, graph, cluster, center, node_colours):
        sub_graph = graph.subgraph(cluster)
        nodes, edges = self.visualiser.visualise(sub_graph, colour_dict=node_colours, center=center)
        return nodes, edges

    def make_cluster_dict(self):
        cluster_dict = {}
        graphs_dict = {}
        num_clusters = 0

        # default is starting at 400, decreasing in steps of -5, all the way to 0
        for score in range(self.initial_alignment_score, self.end_score, self.step):
            graph = self.ssn.get_graph_filtered_edges(score)
            components = nx.connected_components(graph)
            clusters = self._get_clusters(components)
            if len(clusters) != num_clusters:
                cluster_dict[score] = clusters
                graphs_dict[score] = graph
                num_clusters = len(clusters)

        return cluster_dict, graphs_dict

    def get_node_colours(self, clusters_dict):
        groups = self._number_clusters(clusters_dict)
        colours = self._get_group_colours(groups)
        node_colours = {}
        for node, group in groups.items():
            node_colours[node] = colours[str(group)]
        return node_colours

    @staticmethod
    def _number_clusters(cluster_dict):

        cluster_groups_dict = {}
        group_num = 1
        for score, clusters in cluster_dict.items():
            for cluster in clusters:
                cluster_groups = []
                nodes_to_assign = []
                for node in cluster:
                    # Generate list of groups in the cluster
                    if node in cluster_groups_dict:
                        if type(cluster_groups_dict.get(node)) is int:
                            cluster_groups.append(cluster_groups_dict.get(node))
                    else:
                        nodes_to_assign.append(node)

                if len(cluster_groups) == 0:
                    group = group_num
                    group_num += 1
                elif len(set(cluster_groups)) == 1:
                    group = cluster_groups[0]
                else:
                    group = set(cluster_groups)

                for node in cluster:
                    if node not in cluster_groups_dict:
                        cluster_groups_dict[node] = group
        return cluster_groups_dict

    def _get_group_colours(self, groups):
        group_colours = {}
        group_names = groups.values()
        for group in group_names:
            name = str(group)
            if type(group) is int and name not in group_colours:
                colour = self.rndcolgen.generate_new_colour()
                group_colours[name] = colour

        for group in group_names:
            name = str(group)
            if type(group) is set and name not in group_colours:
                colours_to_avg = []
                for shared_group in group:
                    colours_to_avg.append(group_colours[str(shared_group)])
                colour = self.rndcolgen.average_colour(colours_to_avg)
                group_colours[name] = colour

        return group_colours

    def _get_clusters(self, components):
        clusters = []
        for comp in components:
            if len(comp) >= self.cluster_min_nodes:
                clusters.append(list(comp))

        clusters.sort(key=len, reverse=True)
        return list(clusters)

    def _cluster_box_move(self, cluster):
        num_nodes = len(cluster)
        space = num_nodes * self.space_per_node
        return space/2

    @staticmethod
    def _move(i, center, v_move, move, rows):
        if move > v_move:
            v_move = move

        i += 1
        if i % rows == 0 and i != 1:
            center[1] -= v_move
            center[0] = 0
            v_move = 0
        else:
            center[0] += move

        return center, v_move

    def log(self, msg, level=1):
        if level >= self.log_level:
            print(f"SSN_Cluster: {msg}")

class SSN_Visualiser(object):

    def __init__(self, enzyme_type, log_level=0):
        self.enzyme_type = enzyme_type
        self.enzyme_type_obj = EnzymeType.objects(enzyme_type=enzyme_type)[0]
        self.node_metadata = self._find_uniref_metadata()

        self.edge_colour = {'color': 'darkgrey', 'opacity': 0.5}
        self.edge_width = 0.4
        self.uniref_border_width = 1
        self.uniref_border_colour = 'black'
        self.biocatdb_border_width = 2
        self.biocatdb_border_colour = 'darkred'
        self.border_width_selected = 3
        self.node_colour = 'rgba(5, 5, 168, 0.95)'
        self.node_size = 40
        self.node_shape = 'dot'

        self.log_level = log_level

    def visualise(self, graph, colour_dict=None, center=None):
        pos_dict = nx.kamada_kawai_layout(graph, scale=5000, center=center)

        nodes = []
        edges = []
        for name in graph.nodes:
            if colour_dict is None:
                colour = None
            else:
                colour = colour_dict[name]
            nodes.append(self._get_vis_node(name, pos_dict=pos_dict, colour=colour))

        for edge in graph.edges:
            weight = graph.get_edge_data(edge[0], edge[1], default={'weight': 0})['weight']
            edges.append(self._get_vis_edge(edge[0], edge[1], weight))

        nodes = self._sort_biocatdb_nodes_to_front(nodes)

        return nodes, edges

    def _get_vis_node(self, node_name, pos_dict=None, colour=None):
        if colour is None:
            colour = self.node_colour

        if 'UniRef50' in node_name:
            border = self.uniref_border_colour
            border_width = self.uniref_border_width
            node_type = 'uniref'
        else:
            border = self.biocatdb_border_colour
            border_width = self.biocatdb_border_width
            node_type = 'biocatdb'

        metadata = self.node_metadata.get(node_name, {})
        protein_name = metadata.get('protein_name', '')
        tax = metadata.get('tax', '')
        if protein_name != '':
            title = f"{protein_name} - {tax}"
        else:
            title = node_name

        node = {'id': node_name,
                'size': self.node_size,
                'borderWidth': border_width,
                'borderWidthSelected': self.border_width_selected,
                'color': {'background': colour,
                          'border': border,
                          'highlight': {'border': border}},
                'title': title,
                'shape': self.node_shape,
                'node_type': node_type,
                'metadata': metadata}

        if pos_dict is not None:
            x, y = tuple(pos_dict.get(node_name, (0, 0)))
            node['x'] = x
            node['y'] = y

        return node

    def _get_vis_edge(self, edge_one, edge_two, weight):
        #weight = self.graph.get_edge_data(edge_one, edge_two, default={'weight': 0})['weight']
        edge = {'id': f"from {edge_one} to {edge_two}",
                'from': edge_one,
                'to': edge_two,
                'weight': weight,
                'width': self.edge_width,
                'color': self.edge_colour}
        return edge

    def _sort_biocatdb_nodes_to_front(self, vis_nodes):
        """ Returns vis_nodes with any nodes marked as node_type='biocatdb' at the front """

        biocatdb_nodes = []
        other_nodes = []

        for node in vis_nodes:
            if 'biocatdb' in node.get('node_type', ''):
                biocatdb_nodes.append(node)
            else:
                other_nodes.append(node)

        return other_nodes + biocatdb_nodes

    def _find_uniref_metadata(self):
        node_metadata = {}

        unirefs = UniRef50.objects(enzyme_type=self.enzyme_type_obj).exclude('id', 'enzyme_type', 'sequence', "result_of_blasts_for")

        for seq_obj in unirefs:
            node_metadata[seq_obj.enzyme_name] = json.loads(seq_obj.to_json())
        return node_metadata

    def log(self, msg, level=1):
        if level >= self.log_level:
            print(f"SSN_Visualiser: {msg}")

class SSN(object):

    def __init__(self, enzyme_type, aba_blaster=None, log_level=0):

        self.graph = nx.Graph()

        self.enzyme_type = enzyme_type
        self.enzyme_type_obj = EnzymeType.objects(enzyme_type=enzyme_type)[0]

        if aba_blaster is None:
            if log_level > 0:
                print_log = True
            else:
                print_log = False
            self.aba_blaster = AllByAllBlaster(enzyme_type, print_log=print_log)
        else:
            self.aba_blaster = aba_blaster

        self.node_metadata = {}

        self.log_level = log_level

        self.save_path = str(Path(__file__).parents[0]) + f'/analysis_data/ssn/{self.enzyme_type}'
        if not os.path.exists(self.save_path):
            os.mkdir(self.save_path)

        self.log(f"SSN object initialised for {enzyme_type}")

        self.db_ssn = self._get_db_object()

    def save(self):
        t0 = time.time()

        graph_data = nx.to_dict_of_dicts(self.graph)

        att_dict = {}
        for node in list(self.graph):
            att_dict[node] = self.graph.nodes[node]

        self.db_ssn.graph_data.update(graph_data)
        self.db_ssn.node_attributes.update(att_dict)
        self.db_ssn.save()

        t1 = time.time()
        self.log(f"Saved SSN to Mongo, for {self.enzyme_type}, in {round(t1 - t0, 1)} seconds")

    def load(self, include_mutants=True, only_biocatdb=False,):

        t0 = time.time()
        if self.db_ssn.graph_data is None:
            self.log(f"No data saved for {self.enzyme_type} SSN, could not load")
            return False

        self.graph = nx.from_dict_of_dicts(self.db_ssn.graph_data)

        # Nodes with no edges are not in edge list..
        for node in self.db_ssn.node_attributes:
            if node not in self.graph.nodes:
                self._add_protein_node(node)

        nx.set_node_attributes(self.graph, self.db_ssn.node_attributes)

        t1 = time.time()
        self.log(f"Loaded SSN for {self.enzyme_type} in {round(t1 - t0, 1)} seconds")

        if include_mutants is False:
            self.filter_out_mutants()
        if only_biocatdb is True:
            self.filer_out_uniref()

    def add_protein(self, seq_obj):
        """ Add the protein to the graph, along with any proteins which have alignments """

        self.log(f"Adding node - {seq_obj.enzyme_name} and making alignments..")
        t0 = time.time()

        name = seq_obj.enzyme_name
        self._add_protein_node(name, alignments_made=True)
        alignment_names, alignment_scores = self.aba_blaster.get_alignments(seq_obj)
        #self.graph.nodes[name]['attributes']['alignments_made'] = True

        count = 0
        for i, protein_name in enumerate(alignment_names):
            count += self._add_protein_node(protein_name)
            self._add_alignment_edge(seq_obj.enzyme_name, protein_name, alignment_scores[i])

        t1 = time.time()
        self.log(f"{count} new nodes made for alignments, with {len(alignment_names)} edges added")
        self.log(f"Protein {seq_obj.enzyme_name} processed in {round(t1-t0,0)} seconds")

    def add_multiple_proteins(self, list_seq_obj):
        for seq_obj in list_seq_obj:
            self.add_protein(seq_obj)

    def nodes_need_alignments(self, max_num=None):
        """ Return nodes which needs alignments making, maximum of max_num"""

        t0 = time.time()
        need_alignments = []
        count = 0
        for node in list(self.graph.nodes):
            if self.graph.nodes[node]['alignments_made'] == False:
                seq_obj = self._get_sequence_object(node)
                need_alignments.append(seq_obj)
                count += 1
                if count == max_num:
                    break

        t1 = time.time()
        self.log(f"Identified {count} nodes which need alignments making in {round(t1-t0,1)} seconds")

        return need_alignments

    def nodes_not_present(self, only_biocatdb=False, max_num=None):
        """ Return a list of enzymes which are not in the ssn """

        # Get a list of all sequence objects of enzyme type
        t0 = time.time()
        sequences = Sequence.objects(db.Q(enzyme_type=self.enzyme_type) &
                                     db.Q(sequence__ne="") &
                                     db.Q(sequence__ne=None) &
                                     db.Q(sequence_unavailable__ne=True))
        if only_biocatdb is True:
            seq_objects = list(sequences)
        else:
            unirefs = UniRef50.objects(enzyme_type=self.enzyme_type_obj)
            seq_objects = list(sequences) + list(unirefs)

        # Get sequences not in nodes
        not_in_nodes = []
        for seq_obj in seq_objects:
            if seq_obj.enzyme_name not in list(self.graph.nodes):
                if seq_obj.sequence != None:
                    if len(seq_obj.sequence) > 12:
                        not_in_nodes.append(seq_obj)

        # Return only up to the maximum number of sequences
        if max_num != None:
            if len(not_in_nodes) > max_num:
                not_in_nodes = not_in_nodes[0:max_num]

        t1 = time.time()
        self.log(f"Identified {len(not_in_nodes)} {self.enzyme_type} proteins which need adding, in {round(t1 - t0, 1)} seconds")
        return not_in_nodes

    def remove_nonexisting_seqs(self):

        t0 = time.time()
        sequences = Sequence.objects(enzyme_type=self.enzyme_type).distinct('enzyme_name')
        unirefs = UniRef50.objects(enzyme_type=self.enzyme_type_obj).distinct('enzyme_name')
        protein_names = list(sequences) + list(unirefs)
        count = 0
        for node in list(self.graph.nodes):
            if node not in protein_names:
                self.log(f"Node: {node} not in the database - removing")
                self.graph.remove_node(node)
                count += 1

        t1 = time.time()
        self.log(f"Identified {count} sequences which were in SSN but not in database, in {round(t1-t0,1)} seconds")

    def get_graph_filtered_edges(self, min_weight):
        sub_graph = nx.Graph([(u, v, d) for u, v, d in self.graph.edges(data=True) if d['weight'] >= min_weight])
        return sub_graph

    def get_nodes_to_cluster_on(self, starting_score=300, step=-2, min_edges=6):

        t0 = time.time()
        nodes_to_cluster_on = []
        nodes_in_clusters = set([])

        for score in range(starting_score, 0, step):
            graph = self.get_graph_filtered_edges(score)
            edges_dict = {}
            for node in graph.nodes:
                edges = graph.edges(node)
                num_edges = len(edges)

                for edge in edges:
                    # only want edges to and from uniref nodes
                    if ('UniRef' not in edge[0]) or ('UniRef' not in edge[1]):
                        num_edges -= 1

                    # dont count multiple edges to a cluster
                    elif (edge[0] in nodes_in_clusters) or (edge[1] in nodes_in_clusters):
                        num_edges -= 1

                if num_edges >= min_edges:
                    edges_dict[node] = num_edges

            # sort edges dict by number of edges
            sorted_nodes = {nodes: num_edges for nodes, num_edges in
                            sorted(edges_dict.items(), key=lambda item: item[1], reverse=True)}

            for node in sorted_nodes:
                if node not in nodes_in_clusters:
                    cluster = list(graph.neighbors(node)) + [node]
                    for cluster_node in cluster:
                        if ('UniRef50' in cluster_node) and (cluster_node not in nodes_in_clusters):
                            self.graph.nodes[cluster_node]['cluster_group'] = node
                    nodes_to_cluster_on.append(node)
                    nodes_in_clusters.update(cluster)

        t1 = time.time()
        self.log(f"Found {len(nodes_to_cluster_on)} nodes to cluster on with minimum {min_edges} edges in {round(t1-t0,1)} seconds")
        return nodes_to_cluster_on

    def filter_out_mutants(self):
        t0 = time.time()
        mutants = Sequence.objects(db.Q(enzyme_type=self.enzyme_type) &
                                   (db.Q(mutant_of='') | db.Q(mutant_of=None))).distinct('enzyme_name')

        for mutant in list(mutants):
            if mutant in self.graph.nodes:
                self.graph.remove_node(mutant)

        t1 = time.time()
        self.log(f'Filtered mutants from graph in {round(t1-t0,1)} seconds')

    def filer_out_uniref(self):
        t0 = time.time()
        for node in list(self.graph.nodes):
            if 'UniRef50' in node:
                self.graph.remove_node(node)

        t1 = time.time()
        self.log(f'Filtered uniref50 sequences from graph in {round(t1 - t0, 1)} seconds')

    def _add_protein_node(self, node_name, alignments_made=False):
        """ If a protein is not already in the graph, then add it """
        if 'UniRef50' in node_name:
            node_type = 'uniref'
        else:
            node_type = 'biocatdb'

        if node_name not in self.graph.nodes:
            self.graph.add_node(node_name, node_type=node_type,
                                alignments_made=alignments_made)
            return 1

        if alignments_made == True:
            self.graph.nodes[node_name]['alignments_made'] = True

        return 0

    def _add_alignment_edge(self, node_name, alignment_node_name, alignment_score):
        if node_name != alignment_node_name:
            self.graph.add_edge(node_name, alignment_node_name, weight=alignment_score)

    def _get_db_object(self):
        """ Either finds existing db entry for ssn of enzyme type, or makes a new one """

        query = SeqSimNet.objects(enzyme_type=self.enzyme_type_obj)
        if len(query) == 0:
            db_ssn = SeqSimNet(enzyme_type=self.enzyme_type_obj)
        else:
            db_ssn = query[0]

        return db_ssn

    def log(self, msg, level=10):
        if level >= self.log_level:
            print("SSN: " + msg)

    @staticmethod
    def _get_sequence_object(enzyme_name):
        if 'UniRef50' in enzyme_name:
            return UniRef50.objects(enzyme_name=enzyme_name)[0]
        else:
            return Sequence.objects(enzyme_name=enzyme_name)[0]

def task_expand_ssn(enzyme_type, print_log=True, max_num=200):
    current_app.app_context().push()

    aba_blaster = AllByAllBlaster(enzyme_type, print_log=print_log)
    aba_blaster.make_blast_db()

    ssn = SSN(enzyme_type, aba_blaster=aba_blaster, print_log=print_log)
    ssn.load()
    ssn.remove_nonexisting_seqs()

    biocatdb_seqs = ssn.nodes_not_present(only_biocatdb=True, max_num=max_num)
    if len(biocatdb_seqs) != 0:
        ssn.add_multiple_proteins(biocatdb_seqs)
        ssn.save()
        current_app.alignment_queue.enqueue(new_expand_ssn_job, enzyme_type)
        return

    need_alignments = ssn.nodes_need_alignments(max_num=max_num)
    if len(need_alignments) != 0:
        ssn.add_multiple_proteins(need_alignments)
        ssn.save()
        current_app.alignment_queue.enqueue(new_expand_ssn_job, enzyme_type)
        return

    not_present = ssn.nodes_not_present(max_num=max_num)
    if len(not_present) != 0:
        ssn.add_multiple_proteins(not_present)
        ssn.save()
        current_app.alignment_queue.enqueue(new_expand_ssn_job, enzyme_type)

        return

    enz_type_obj = EnzymeType.objects(enzyme_type=enzyme_type)[0]
    enz_type_obj.bioinformatics_status = 'Idle'
    enz_type_obj.save()

def new_expand_ssn_job(enzyme_type):

    active_process_jobs = list(StartedJobRegistry(queue=current_app.alignment_queue).get_job_ids())
    active_process_jobs.extend(current_app.alignment_queue.job_ids)

    job_name = f"{enzyme_type}_expand_ssn"
    if job_name not in active_process_jobs:
        current_app.alignment_queue.enqueue(task_expand_ssn, enzyme_type, job_id=job_name)


if __name__ == '__main__':
    from retrobiocat_web.mongo.default_connection import make_default_connection
    make_default_connection()

    aad_ssn = SSN('AAD', log_level=1)
    aad_ssn.load()

    aad_c = SSN_Clusterer('AAD', aad_ssn, cluster_min_nodes=10, log_level=1)
    vis_dict = aad_c.make_visualisations()

    for score, nodes_and_edges in vis_dict.items():
        print(f"--- Alignment score {score} ---")
        print(nodes_and_edges[0])

    # 1. Set minimum number of nodes for a cluster
    # 2. Move down alignment score.  For each score where there is a different number of scores, visualise this.



