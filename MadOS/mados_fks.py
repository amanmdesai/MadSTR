###################################################
#                                                   #
# Source file of some auxiliary function related to #
# the FKS modules for the MadOS plugin of MG5aMC.   #
#                                                   #
#####################################################

import copy
import logging

import madgraph.core.base_objects as MG
import madgraph.core.diagram_generation as diagram_generation
import madgraph.core.helas_objects as helas_objects
import madgraph.fks.fks_helas_objects as fks_helas
from madgraph import InvalidCmd


logger = logging.getLogger('MadOS_plugin.mados_fks')


class FKSHelasMultiProcessWithOS(fks_helas.FKSHelasMultiProcess):
    """a class for FKS Helas processes with OS singularities
    """

    def __init__(self, fksmulti, **args):
        """initialise as a FKSMultiProcess, then add the OS informations
        """
        super(FKSHelasMultiProcessWithOS, self).__init__(fksmulti, args)
        # now one has to add the OS informations
        # this may not be the best/most optimal way to go, but at least
        # requires no changes in the core fks stuff
        for born in fksmulti['born_processes']:
            for real in born.real_amps:
                if not real.os_amplitudes:
                    continue
                #now we have to find the matching born and real 
                # in the helas process
                for born_me in self['matrix_elements']:
                    if not born.born_proc in born_me.born_matrix_element['processes']:
                        continue
                    for real_me in born_me.real_processes:
                        if not real.process in real_me.matrix_element['processes']:
                            continue
                        real_me.os_ids = real.os_ids
                        real_me.os_diagrams = real.os_diagrams
                        real_me.os_matrix_elements = [\
                            helas_objects.HelasDecayChainProcess(os_amp).combine_decay_chain_processes()[0]
                            for os_amp in real.os_amplitudes]


    def get_used_lorentz(self):
        """the get_used_lorentz function. 
        Use the mother class, plus check the os matrix elements
        """
        lorentz_list = super(FKSHelasMultiProcessWithOS, self).get_used_lorentz()
        for real in self.real_processes:
            for os_real in real.os_matrix_elements:
                lorentz_list.extend(os_real.get_used_lorentz())
        return list(set(lorentz_list))


    def get_used_couplings(self):
        """the get_used_couplings function
        Use the mother class, plus check the os matrix elements
        """
        coupl_list = super(FKSHelasMultiProcessWithOS, self).get_used_couplings()
        for real in self.real_processes:
            for os_real in real.os_matrix_elements:
                coupl_list.extend([c for c in os_real.get_used_couplings()])
        return coupl_list    


    def add_process(self, other):
        """ add two processes
        Use the mother class, plus check the os matrix elements
        """
        super(FKSHelasMultiProcessWithOS, self).add_process(other)
        # now the OS diagrams
        for oth_real in other.real_processes:
            for oth_on_shell in oth_real.os_matrix_elements:
                this_on_shell = this_real.os_matrix_elements[
                        this_real.os_matrix_elements.index(oth_on_shell)]
                this_pdgs = [[leg['id'] for leg in proc['legs']] \
                    for proc in this_on_shell['processes']]
                for oth_proc in oth_on_shell['processes']:
                    oth_pdgs = [leg['id'] for leg in oth_proc['legs']]
                    if oth_pdgs not in this_pdgs:
                        this_on_shell['processes'].append(oth_proc)
                        this_pdgs.append(oth_pdgs)


    def get_os_ids(self):
        """Returns the list of the fks infos for all processes in the format
        {n_me, pdgs, fks_info}, where n_me is the number of real_matrix_element the configuration
        belongs to"""
        os_ids = []
        for real in self.real_processes:
            # append only the mother particle, i.e. the 1st particle in each list of ids
            os_ids += [ids[0] for ids in real.os_ids]
        return set(os_ids)




def find_os_divergences(fksreal):
    """this function looks for possible on shell contributions 
    to be removed.
    In order to be agnostic on mass hierarchies all splittings
    1->2 3 are investigated, with m1 != 0, m2, m3 != m1
    since these resonances are introduced at the real-emission
    level, one must have m2=0 or m3=0
    """
    model = fksreal.process['model']
    # take account of the orders for the on shell processes
    weighted_order = fksreal.process['orders']['WEIGHTED']

    fksreal.os_amplitudes = []
    fksreal.os_ids = []
    fksreal.os_diagrams = []

    # this is a counter to be returned
    n_os = 0

    # focus only on final state legs
    final_legs = [copy.copy(l) for l in fksreal.process['legs'] if l['state']]
    for leg_2 in final_legs:
        for leg_3 in [l for l in final_legs if l['number'] > leg_2['number']]:
            # one of the two legs must be massless
            if not leg_2['massless'] and not leg_3['massless']:
                continue
            # prepare the leglist for the 'on shell' process, which should
            # not contain leg_2 and leg_3, but should contain their mother particle
            # if it exists
            other_legs = [copy.copy(l) for l in fksreal.process['legs'] if \
                    l != leg_2 and l != leg_3]
            assert(len(other_legs) == (len(fksreal.process['legs']) - 2))
            leg_2_part = model.get('particle_dict')[leg_2['id']]
            leg_3_part = model.get('particle_dict')[leg_3['id']]
            interactions = [inte for inte in model.get('interaction_dict').values() \
                            if len(inte['particles']) == 3 and \
                                leg_2_part in inte['particles'] and \
                                leg_3_part in inte['particles']]

            for inte in interactions:
                particles = [copy.copy(p) for p in inte['particles']]
                try:
                    particles.remove(leg_2_part)
                    particles.remove(leg_3_part)
                except ValueError:
                    # this is when leg_2 and leg_3 are the same particle
                    # and it appears only once in the interacion, so
                    # the interaction has to be skipped
                    continue
                leg_1_part = particles[0]
                # check that it is massive and its mass it is different from
                # leg_2 and leg_3
                if leg_1_part['mass'].lower() == 'zero' or \
                   leg_1_part['mass'] == leg_2_part['mass'] or \
                   leg_1_part['mass'] == leg_3_part['mass']:
                    continue
                # this should be the final particle (take the antiparticle as
                # it has to go "into" the interaction)

                leg_1 = MG.Leg({'state' : True,
                                'id' : leg_1_part.get_anti_pdg_code(),
                                'number': leg_2['number']})

                os_legs = [copy.copy(l) for l in other_legs]
                os_legs.insert(leg_2['number'] - 1, leg_1)
                assert(len(os_legs) == (len(fksreal.process['legs']) - 1))
                # count the occurences of leg 1 in the final state legs
                # only one of them has to be decayed
                nleg_1 = [l['id'] for l in os_legs].count(leg_1['id'])
                # construct the decay chain and the process
                # definition
                leg_1_decay = MG.Leg({'id': leg_1['id'], 'state': False})
                leg_2_decay = MG.Leg({'id': leg_2['id'], 'state': True})
                leg_3_decay = MG.Leg({'id': leg_3['id'], 'state': True})
                decay_chain_legs = MG.LegList(\
                                   [leg_1_decay, leg_2_decay, leg_3_decay])
                decay_chain = MG.Process(\
                              {'model': model,
                               'legs': MG.LegList(decay_chain_legs),
                               'is_decay_chain': True})

                # construct the 'trivial' decay chain to be used when leg_1
                # occurs more than once in the final state legs
                leg_1_decayed = MG.Leg({'id': leg_1['id'], 'state': True})
                trivial_decay_chain_legs = MG.LegList(\
                                   [leg_1_decay, leg_1_decayed])
                trivial_decay_chain = MG.Process(\
                              {'model': model,
                               'legs': MG.LegList(trivial_decay_chain_legs),
                               'is_decay_chain': True})
                
                decay_chains = MG.ProcessList([decay_chain] + \
                                    [trivial_decay_chain] * (nleg_1 - 1))

                for leg in os_legs:
                    leg['number'] = os_legs.index(leg) + 1
                # the orders in os_procdef refer only to the production process
                # so the orders of the splitting have to be subtracted
                prod_weighted_order = weighted_order - \
                        sum([v * model.get('order_hierarchy')[o] \
                             for o, v in inte['orders'].items()])
                os_procdef =  MG.Process(\
                             {'model': model,
                              'legs': MG.LegList(os_legs),
                              'decay_chains': decay_chains,
                              'orders': {'WEIGHTED': prod_weighted_order}})
                # now generate the amplitude. 
                # Do nothing if any InvalidCmd is raised (e.g. charge not conserved)
                # or if no diagrams are there
                # set the logger to CRITICAL in order not to warn about 1 -> 1
                # (trivial) decay chains
                
                loglevel = logging.getLogger('madgraph.diagram_generation').level
                logging.getLogger('madgraph.diagram_generation').setLevel(logging.CRITICAL)
                try:
                    os_amp = diagram_generation.DecayChainAmplitude(os_procdef)
                except InvalidCmd:
                    continue
                logging.getLogger('madgraph.diagram_generation').setLevel(loglevel)
                
                if not all([amp['diagrams'] for amp in os_amp['amplitudes']]):
                    continue
                logger.info('Process %s has been generated for on-shell subtraction'
                        % os_procdef.input_string())
                n_os+= 1
                fksreal.os_amplitudes.append(os_amp)
                fksreal.os_ids.append([leg_1['id'], leg_2['id'], leg_3['id']])
                fksreal.os_diagrams.append(find_os_diagrams(\
                        fksreal.amplitude, [leg_1, leg_2, leg_3]))
    return n_os


def find_os_diagrams(amp, legs):
    """ return the diagram number of the diagrams which correspond to the production
    x decay (legs[0] -> legs[1] -> legs[2]
    """
    mom, dau1, dau2 = legs
    os_diagrams = []

    for i, diag in enumerate(amp['diagrams']):
        for vert in diag['vertices']:
            ids = [abs(l['id']) for l in vert['legs']]
            if dau1 in vert['legs'] and dau2 in vert['legs'] and abs(mom['id']) in ids:
                os_diagrams.append(i)

    return os_diagrams
