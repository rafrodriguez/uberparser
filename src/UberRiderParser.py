#!/usr/bin/env python

# Python imports
import sys
import re
from datetime import datetime
import copy

# Other imports
import pandas as pd
from pandas import DataFrame

class UberRiderParser:
    """Parser of Uber Riders webpage.

    As of January 2018 Uber Riders webpage lacks a "Export to CSV" option
    and the information is shown in a poor format, namely:
    - Costs 0 are shown as empty string instead of a 0
    - The message 'Canceled' is shown on a separate row
    - Splitted fares are identified with a text below the date and in a
      separate row
    - Depending on who requested the trip, one can notice the split in either
      "This trip was requested by" or in "You split this fare with"
      splitting fare)
    - Dates use the format MM/DD/YY (what is this, 1900?)

    The module implements a method that converts a file with the webscrapped
    data and returns a pandas DataFrame.

    Args:
        filename (str): filename of a file with webscrapped information of the
            rides summary pages of Uber Riders webpage

    Example:
        >>> from UberRiderParser import UberRiderParser
        >>> parser = UberRiderParser(input_filename)
        >>> df = parser.as_df()
    
    Note:
        This module can be executed as follows to take a filename as input and
        save a .xls file with the information of the file:
        $ ./UberRiderParser.py webscrappedData.txt 

        The fare is taken as shown in the main table in the webpage, which does
        not consider split fare. 
        It is not possible to infer the actual paid amount without opening the
        details of every single trip because the summary table, from where this
        module assumes the data was scrapped, shows the fare before split(if 
        any) and when split, it sometimes appears as "split fare with" and 
        sometimes as "requested by", and lists at most one person, even when it
        was split with more than one.
        It is advisable to take the output of this module as is and manually
        check the rows where the columns requested_by or split_with are not
        empty.
    """

    def __init__(self, filename):
        self.filename = filename
        self.separator = ';'
        # These are the "base" available columns for every ride, as shown on
        # Uber web
        self.columns = ['date',
                        'driver',
                        'fare',
                        'ride_type',
                        'city',
                        'payment']

    def _split_by_pattern(self, string, pattern):
        # Store the begin positions of the segments
        segment_begins = [match.span()[0] for match in re.finditer(pattern, 
                                                                   string)]
        # Add a dummy "begin" that will serve as end limit for the last elem
        segment_begins.append(len(string))
        
        # Define the begin and end for each segment
        segment_limits = [(segment_begins[i], segment_begins[i+1]) 
                          for i in range(0, len(segment_begins)-1)]

        # Do the actual split
        lines = [string[pos[0]:pos[1]] for pos in segment_limits]
        return lines
    
    def _handle_optional_column(self, line, text_pattern, col_name):
        """Looks for text_pattern in each of the elements (columns) of the line
        and if found, moves it to the corresponding position of the column 
        col_name"""
        # Search for the text in each of the elements of the line
        search_results = [col.find(text_pattern) for col in line]
        bool_found_here = [True if x != -1 else False for x in search_results]
        if sum(bool_found_here) != 1:
            # Text not present in any of the elements of the line, add a new
            # empty column
            text_to_insert = ''
        else:
            # Text is present
            index_element_to_move = bool_found_here.index(True)
            text_to_insert = copy.copy(line[index_element_to_move])

            # Remove the element that will be moved into a new column
            del(line[index_element_to_move])

        # Add the value
        column_index = self.columns.index(col_name)
        line[column_index] = text_to_insert

        # Return the modified line
        return line

    def _read_file_as_list_of_lists(self):
        # The webpage displays some information in multiple lines. Combine them 
        # into a string then split them
        with open(self.filename) as f:
            lines = f.readlines()
        
        # Strip by the left, not by right because it would mess with multiline
        # data
        lines = [line.lstrip() for line in lines]
        file_as_string = ''.join(lines)
        
        # Case where info is shown in multiple rows
        file_as_string = file_as_string.replace('\n', '\t')
        
        # Replace double spaces with single space
        file_as_string = file_as_string.replace('  ', ' ')

        # Split the string to get individual lines
        uber_date_pattern = r'[0-9][0-9]/[0-9][0-9]/[0-9][0-9]'
        lines = self._split_by_pattern(file_as_string, uber_date_pattern)
        
        # Split each of the individual lines
        # Given that the webpage displays nothing for some empty values, using
        # regex would be a mess, so the tabs will be used as column indicators
        lines = [line.strip() for line in lines]
        lines = [line.split('\t') for line in lines]
        
        # Handle the columns that are only present in some lines and are not
        # properly separated
        # optional_cols has tuples of the form:
        # (<text pattern to identify the value>, <column name to add>)
        optional_cols =  [('You split this fare with', 'split_with'),
                          ('This trip was requested by', 'requested_by'),
                          ('Canceled', 'canceled')]
        self.columns += [elem[1] for elem in optional_cols]
        lines = [line + ['']*len(optional_cols) for line in lines]
        for pattern, col_name in optional_cols:
            for line in lines:
                line = self._handle_optional_column(line, pattern, col_name)

        return lines

    def as_df(self):
        """Parses the file point by self.filename into a pandas DataFrame.

        Returns:
            DataFrame: pandas DataFrame with the information contained in
                self.filename.
        """        
        table = self._read_file_as_list_of_lists()
        df = DataFrame(table)
        df.columns = self.columns

        # Fix date format
        df['date'] = pd.to_datetime(df['date'],infer_datetime_format=True)

        # Split fare column in currency and fare
        # This fare is total (as displayed on Uber Riders webpage summmary) and
        # does not take into account split fares (and it is indeed impossible
        # to know the actual paid fare without clicking on View Details for
        # each ride, doing that would require a more complicated logic and web
        # parsing logic)
        df['currency'], df['fare'] = \
        zip(*df['fare'].apply(lambda x: x.split('$', 1)
                              if "$" in x else [None, 0.0]))
        df['currency'] = df['currency'].apply(lambda x:
        x.replace(' ', '') if x is not None else None)
        
        # Make column canceled boolean
        df['canceled'] = df['canceled'].apply(lambda x: True if x == 'Canceled'
                                             else False)
        # Clean split_with column
        df['split_with'] = df['split_with'].apply(lambda x:
        x.replace('You split this fare with ', '') if 'split this' in x 
        else None)

        # Clean requested_by column
        df['requested_by'] = df['requested_by'].apply(lambda x:
        x.replace('This trip was requested by ', '') if 'requested by' in x 
        else None)

        # Column selection
        df = df[['date', 'driver', 'ride_type', 'city', 'payment', 
                 'split_with', 'requested_by', 'canceled', 'currency', 
                 'fare', ]]
        
        # datatypes
        df = df.infer_objects()
        df['fare'] = pd.to_numeric(df['fare'])
        return df

if __name__ == '__main__':
    input_filename = sys.argv[1]
    parser = UberRiderParser(input_filename)
    df = parser.as_df()
    output_filename = datetime.today().isoformat().replace(':', '-')[0:16]
    output_filename += '.xls'
    writer = pd.ExcelWriter(output_filename)
    df.to_excel(writer, 'sheet1')
    writer.save()
    print("Saved ", output_filename)
