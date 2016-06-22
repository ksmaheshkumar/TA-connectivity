"""
-------------------------------------------------------------------------------
Name:       connect.py
Purpose:    Test application availability at a given port
Author:     seunomosowon
Created:    11/01/2013
Updated:    18/06/2016
Copyright:  (c) seunomosowon 2016
Licence:    Creative Commons BY 3.0
-------------------------------------------------------------------------------
"""

# module imports
import os
import csv
import sys
from splunklib.modularinput import *
from connectivity_lib.connect_test import *
from connectivity_lib.constants import *
from multiprocessing import Pool


class Connect(Script):
    """
    This class contains all methods required for the modular input
    """

    def get_scheme(self):
        """This overrides the super method from the parent class"""
        scheme = Scheme("Connect")
        scheme.description = "Test availability of service on a specific port"
        scheme.use_external_validation = True
        name = Argument(
            name="name",
            description="Lookup file",
            data_type=Argument.data_type_string,
            required_on_edit=True,
            required_on_create=True
        )
        scheme.add_argument(name)
        host_field = Argument(
            name="host_field",
            description="Define field name to use as hostnames from the lookup file",
            data_type=Argument.data_type_string,
            required_on_edit=True,
            required_on_create=True
        )
        scheme.add_argument(host_field)
        port_field = Argument(
            name="port_field",
            description="Define field name to use as destination port number for the connectivity test",
            data_type=Argument.data_type_string,
            required_on_edit=False,
            required_on_create=False
        )
        scheme.add_argument(port_field)
        workers = Argument(
            name="workers",
            description="Define number of worker threads to use for this input",
            data_type=Argument.data_type_number,
            validation="is_pos_int('workers')",
            required_on_edit=False,
            required_on_create=False
        )
        scheme.add_argument(workers)
        return scheme

    def validate_input(self, validation_definition):
        """
        Check if lookup defined in inputs exists
        Check if host_field defined matches a header field in the csv.
        """
        csv_headers = set()
        lookup_file = validation_definition.metadata['name']
        host_field = validation_definition.parameters['host_field']
        if not os.path.isfile(lookup_file):
            raise ConnectivityExceptionFileNotFound(lookup_file)
        csvin = csv.reader(lookup_file)
        csv_headers.update(next(csvin, []))
        if host_field not in csv_headers:
            raise ConnectivityExceptionFieldNotFound(host_field)
        if 'port_field' in validation_definition.parameters.keys():
            port_field = validation_definition.parameters['port_field']
            if port_field is not None and port_field != '' and port_field not in csv_headers:
                raise ConnectivityExceptionFieldNotFound(port_field)

    def disable_input(self, input_name):
        """
        This disables a modular input given the input name.
        :param input_name: Name of input that needs to be disabled.
            This must be the input name just after the scheme - 'scheme://input_name_without_scheme'
        :type input_name: basestring
        :return: Returns the disabled input
        :rtype: Entity
        """
        self.service.inputs[input_name].disable()

    def stream_events(self, inputs, ew):
        """This function handles all the action: splunk calls this modular input
        without arguments, streams XML describing the inputs to stdin, and waits
        for XML on stdout describing events.
        If you set use_single_instance to True on the scheme in get_scheme, it
        will pass all the instances of this input to a single instance of this
        script.
        :param inputs: an InputDefinition object
        :param ew: an EventWriter object
        """
        for input_name, input_item in inputs.inputs.iteritems():
            lookup_path = input_name.split('://')[1]
            host_field = input_item['host_field']
            if 'port_field' in input_item.keys():
                port_field = input_item['port_field']
            else:
                port_field = None
                ew.log(EventWriter.DEBUG,
                       "port_field not found in configuration. host_field should have socket included")
            num_of_workers = int(input_item['workers'])
            if num_of_workers < 0 or num_of_workers is None:
                num_of_workers = NUM_OF_WORKER_PROCESSES

            with open(lookup_path) as hosts:
                reader = csv.DictReader(hosts)
                if host_field in reader.fieldnames:
                    pool = Pool(processes=num_of_workers)
                    if port_field is not None and port_field in reader.fieldnames:
                        results = [pool.apply_async(
                            connect_test, [eachline[host_field].strip('\"\r\n'),
                                           eachline[port_field].strip('\"\r\n')]) for eachline in reader]
                    else:
                        """Do connect_test(eachline[host_field]) asynchronously num_of_workers times"""
                        results = [pool.apply_async(connect_test, eachline[host_field].strip('\"\r\n').split(':'))
                                   for eachline in reader]
                    for x in results:
                        event = Event()
                        event.stanza = input_name
                        event.data = x.get()
                        ew.write_event(event)
                else:
                    self.disable_input(lookup_path)
                    ew.log(EventWriter.ERROR, "Disabling input because host_field not found in header")
                    raise ConnectivityExceptionFieldNotFound(host_field)

if __name__ == "__main__":
    sys.exit(Connect().run(sys.argv))
