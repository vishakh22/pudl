"""
The Public Utility Data Liberation (PUDL) project core module.

The PUDL project integrates several different public data sets into one well
normalized database allowing easier access and interaction between all of them.
This module defines database tables using the SQLAlchemy Object Relational
Mapper (ORM) and initializes the database from several sources:

 - US Energy Information Agency (EIA):
   - Form 860 (eia860)
   - Form 861 (eia861)
   - Form 923 (eia923)
 - US Federal Energy Regulatory Commission (FERC):
   - Form 1 (ferc1)
   - Form 714 (ferc714)
 - US Environmental Protection Agency (EPA):
   - Air Market Program Data (epaampd)
   - Greenhouse Gas Reporting Program (epaghgrp)
"""

import pandas as pd
import numpy as np

from sqlalchemy.sql import select
from sqlalchemy.engine.url import URL
from sqlalchemy import create_engine
from sqlalchemy import Integer, String, Numeric, Boolean, Float

from pudl import settings
from pudl.ferc1 import db_connect_ferc1, cleanstrings, ferc1_meta
from pudl.eia923 import get_eia923_page, yearly_to_monthly_eia923
from pudl.constants import ferc1_fuel_strings, us_states, prime_movers
from pudl.constants import ferc1_fuel_unit_strings, rto_iso
from pudl.constants import ferc1_type_const_strings, ferc1_plant_kind_strings
from pudl.constants import ferc1_default_tables, ferc1_pudl_tables
from pudl.constants import ferc1_working_tables
from pudl.constants import ferc_electric_plant_accounts
from pudl.constants import ferc_accumulated_depreciation
from pudl.constants import month_dict_2015_eia923

# Tables that hold constant values:
from pudl.models import Fuel, FuelUnit, Month, Quarter, PrimeMover, Year
from pudl.models import State, RTOISO
from pudl.constants import census_region, nerc_region
from pudl.constants import fuel_type_aer_eia923, respondent_frequency_eia923

# EIA specific lists that will get moved over to models_eia923.py
from pudl.constants import sector_eia, contract_type_eia923
from pudl.constants import fuel_type_eia923, prime_movers_eia923
from pudl.constants import fuel_units_eia923, energy_source_eia923
from pudl.constants import fuel_group_eia923
from pudl.constants import coalmine_type_eia923, coalmine_state_eia923
from pudl.constants import natural_gas_transport_eia923
from pudl.constants import transport_modes_eia923
from pudl.constants import pagemap_eia923
from pudl.constants import eia923_pudl_tables

# Tables that hold constant values:
from pudl.models import Fuel, FuelUnit, Month, Quarter, PrimeMover, Year
from pudl.models import State, RTOISO, CensusRegion, NERCRegion

# EIA specific lists stored in models_eia923.py
from pudl.models_eia923 import SectorEIA, ContractTypeEIA923
from pudl.models_eia923 import EnergySourceEIA923
from pudl.models_eia923 import CoalMineTypeEIA923, CoalMineStateEIA923
from pudl.models_eia923 import NaturalGasTransportEIA923
from pudl.models_eia923 import TransportModeEIA923
from pudl.models_eia923 import RespondentFrequencyEIA923
from pudl.models_eia923 import PrimeMoverEIA923, FuelTypeAER
from pudl.models_eia923 import FuelTypeEIA923
from pudl.models_eia923 import FuelGroupEIA923, FuelUnitEIA923
from pudl.models_eia923 import PlantInfoEIA923, BoilersEIA923
from pudl.models_eia923 import BoilerFuelEIA923

# Tables that hold "glue" connecting FERC1 & EIA923 to each other:
from pudl.models import Utility, UtilityFERC1, UtilityEIA923
from pudl.models import Plant, PlantFERC1, PlantEIA923
from pudl.models import UtilPlantAssn

# The declarative_base object that contains our PUDL DB MetaData
from pudl.models import PUDLBase


###############################################################################
###############################################################################
# DATABASE CONNECTION & HELPER FUNCTIONS
###############################################################################
###############################################################################


def db_connect_pudl(testing=False):
    """Connect to the PUDL database global settings from settings.py."""
    if(testing):
        return create_engine(URL(**settings.DB_PUDL_TEST))
    else:
        return create_engine(URL(**settings.DB_PUDL))


def create_tables_pudl(engine):
    """Create the tables associated with the PUDL Database."""
    PUDLBase.metadata.create_all(engine)


def drop_tables_pudl(engine):
    """Drop all the tables associated with the PUDL Database and start over."""
    PUDLBase.metadata.drop_all(engine)


###############################################################################
###############################################################################
#   BEGIN INGESTING STATIC & INFRASTRUCTURE TABLES
###############################################################################
###############################################################################


def ingest_static_tables(engine):
    """Populate static PUDL tables with constants for use as foreign keys."""
    from sqlalchemy.orm import sessionmaker

    PUDL_Session = sessionmaker(bind=engine)
    pudl_session = PUDL_Session()

    # Populate tables with static data from above.
    pudl_session.add_all([Fuel(name=f) for f in ferc1_fuel_strings.keys()])
    pudl_session.add_all([FuelUnit(unit=u) for u in
                          ferc1_fuel_unit_strings.keys()])
    pudl_session.add_all([Month(month=i + 1) for i in range(12)])
    pudl_session.add_all(
        [Quarter(q=i + 1, end_month=3 * (i + 1)) for i in range(4)])
    pudl_session.add_all([PrimeMover(prime_mover=pm) for pm in prime_movers])
    pudl_session.add_all([RTOISO(abbr=k, name=v) for k, v in rto_iso.items()])
    pudl_session.add_all([Year(year=yr) for yr in range(1994, 2017)])
    pudl_session.add_all(
        [CensusRegion(abbr=k, name=v) for k, v in census_region.items()])
    pudl_session.add_all(
        [NERCRegion(abbr=k, name=v) for k, v in nerc_region.items()])
    pudl_session.add_all(
        [RespondentFrequencyEIA923(abbr=k, unit=v)
         for k, v in respondent_frequency_eia923.items()])
    pudl_session.add_all(
        [SectorEIA(id=k, name=v) for k, v in sector_eia.items()])
    # pudl_session.add_all(
    #     [ContractTypeEIA923(abbr=k, contract_type=v)
    #      for k, v in contract_type_eia923.items()])
    pudl_session.add_all(
        [FuelTypeEIA923(abbr=k, fuel_type=v)
         for k, v in fuel_type_eia923.items()])
    pudl_session.add_all(
        [PrimeMoverEIA923(abbr=k, prime_mover=v)
         for k, v in prime_movers_eia923.items()])
    pudl_session.add_all(
        [FuelUnitEIA923(abbr=k, unit=v)
         for k, v in fuel_units_eia923.items()])
    pudl_session.add_all(
        [FuelTypeAER(abbr=k, fuel_type=v)
         for k, v in fuel_type_aer_eia923.items()])
    pudl_session.add_all(
        [EnergySourceEIA923(abbr=k, source=v)
         for k, v in energy_source_eia923.items()])
    pudl_session.add_all(
        [FuelGroupEIA923(group=gr) for gr in fuel_group_eia923])
    pudl_session.add_all(
        [CoalMineTypeEIA923(abbr=k, name=v)
         for k, v in coalmine_type_eia923.items()])
    pudl_session.add_all(
        [CoalMineStateEIA923(abbr=k, state=v)
         for k, v in coalmine_state_eia923.items()])
    pudl_session.add_all(
        [CoalMineStateEIA923(abbr=k, state=v)
         for k, v in us_states.items()])  # is this right way to add these?
    pudl_session.add_all(
        [TransportModeEIA923(abbr=k, mode=v)
         for k, v in transport_modes_eia923.items()])
    pudl_session.add_all(
        [NaturalGasTransportEIA923(abbr=k, status=v)
         for k, v in natural_gas_transport_eia923.items()])

    # States dictionary is defined outside this function, below.
    pudl_session.add_all([State(abbr=k, name=v) for k, v in us_states.items()])

    # Commit the changes to the DB and close down the session.
    pudl_session.commit()
    pudl_session.close_all()

    # We aren't bringing row_number in to the PUDL DB:
    ferc_accts_df = ferc_electric_plant_accounts.drop('row_number', axis=1)
    # Get rid of excessive whitespace introduced to break long lines (ugh)
    ferc_accts_df.ferc_account_description = \
        ferc_accts_df.ferc_account_description.str.replace('\s+', ' ')

    ferc_accts_df.rename(columns={'ferc_account_id': 'id',
                                  'ferc_account_description': 'description'},
                         inplace=True)

    ferc_accts_df.to_sql('ferc_accounts',
                         con=engine, index=False, if_exists='append',
                         dtype={'id': String,
                                'description': String})

    ferc_depreciation_lines_df = \
        ferc_accumulated_depreciation.drop('row_number', axis=1)

    ferc_depreciation_lines_df.\
        rename(columns={'line_id': 'id',
                        'ferc_account_description': 'description'},
               inplace=True)

    ferc_depreciation_lines_df.\
        to_sql('ferc_depreciation_lines',
               con=engine, index=False, if_exists='append',
               dtype={'id': String,
                      'description': String})


def ingest_glue_tables(engine):
    """
    Populate the tables which relate the EIA & FERC datasets to each other.

    internal PUDL IDs, for both plants and utilities, so that we don't need
    to use those poorly defined relationships any more.  These mappings were
    largely determined by hand in an Excel spreadsheet, and so may be a
    little bit imperfect. We're pulling that information in from the
    "results" directory...
    """
    import os.path

    map_eia923_ferc1_file = os.path.join(settings.PUDL_DIR,
                                         'results',
                                         'id_mapping',
                                         'mapping_eia923_ferc1.xlsx')

    plant_map = pd.read_excel(map_eia923_ferc1_file, 'plants_output',
                              na_values='', keep_default_na=False,
                              converters={'plant_id': int,
                                          'plant_name': str,
                                          'respondent_id_ferc1': int,
                                          'respondent_name_ferc1': str,
                                          'plant_name_ferc1': str,
                                          'plant_id_eia923': int,
                                          'plant_name_eia923': str,
                                          'operator_name_eia923': str,
                                          'operator_id_eia923': int})

    utility_map = pd.read_excel(map_eia923_ferc1_file, 'utilities_output',
                                na_values='', keep_default_na=False,
                                converters={'utility_id': int,
                                            'utility_name': str,
                                            'respondent_id_ferc1': int,
                                            'respondent_name_ferc1': str,
                                            'operator_id_eia923': int,
                                            'operator_name_eia923': str})

    # We need to standardize plant names -- same capitalization and no leading
    # or trailing white space... since this field is being used as a key in
    # many cases. This also needs to be done any time plant_name is pulled in
    # from other tables.
    plant_map['plant_name_ferc1'] = plant_map['plant_name_ferc1'].str.strip()
    plant_map['plant_name_ferc1'] = plant_map['plant_name_ferc1'].str.title()

    plants = plant_map[['plant_id', 'plant_name']]
    plants = plants.drop_duplicates('plant_id')

    plants_eia923 = plant_map[['plant_id_eia923',
                               'plant_name_eia923',
                               'plant_id']]
    plants_eia923 = plants_eia923.drop_duplicates('plant_id_eia923')
    plants_ferc1 = plant_map[['plant_name_ferc1',
                              'respondent_id_ferc1',
                              'plant_id']]
    plants_ferc1 = plants_ferc1.drop_duplicates(['plant_name_ferc1',
                                                 'respondent_id_ferc1'])
    utilities = utility_map[['utility_id', 'utility_name']]
    utilities = utilities.drop_duplicates('utility_id')
    utilities_eia923 = utility_map[['operator_id_eia923',
                                    'operator_name_eia923',
                                    'utility_id']]
    utilities_eia923 = utilities_eia923.drop_duplicates('operator_id_eia923')

    utilities_ferc1 = utility_map[['respondent_id_ferc1',
                                   'respondent_name_ferc1',
                                   'utility_id']]
    utilities_ferc1 = utilities_ferc1.drop_duplicates('respondent_id_ferc1')

    # Now we need to create a table that indicates which plants are associated
    # with every utility.

    # These dataframes map our plant_id to FERC respondents and EIA
    # operators -- the equivalents of our "utilities"
    plants_respondents = plant_map[['plant_id', 'respondent_id_ferc1']]
    plants_operators = plant_map[['plant_id', 'operator_id_eia923']]

# Here we treat the dataframes like database tables, and join on the
# FERC respondent_id and EIA operator_id, respectively.
    utility_plant_ferc1 = utilities_ferc1.\
        join(plants_respondents.
             set_index('respondent_id_ferc1'),
             on='respondent_id_ferc1')

    utility_plant_eia923 = utilities_eia923.join(
        plants_operators.set_index('operator_id_eia923'),
        on='operator_id_eia923')

    # Now we can concatenate the two dataframes, and get rid of all the columns
    # except for plant_id and utility_id (which determine the  utility to plant
    # association), and get rid of any duplicates or lingering NaN values...
    utility_plant_assn = pd.concat([utility_plant_eia923, utility_plant_ferc1])
    utility_plant_assn = utility_plant_assn[['plant_id', 'utility_id']].\
        dropna().drop_duplicates()

    # At this point there should be at most one row in each of these data
    # frames with NaN values after we drop_duplicates in each. This is because
    # there will be some plants and utilities that only exist in FERC, or only
    # exist in EIA, and while they will have PUDL IDs, they may not have
    # FERC/EIA info (and it'll get pulled in as NaN)

    for df in [plants_eia923, plants_ferc1, utilities_eia923, utilities_ferc1]:
        assert df[pd.isnull(df).any(axis=1)].shape[0] <= 1
        df.dropna(inplace=True)

    # Before we start inserting records into the database, let's do some basic
    # sanity checks to ensure that it's (at least kind of) clean.
    # INSERT SANITY HERE

    # Any FERC respondent_id that appears in plants_ferc1 must also exist in
    # utils_ferc1:
    # INSERT MORE SANITY HERE

    plants.rename(columns={'plant_id': 'id', 'plant_name': 'name'},
                  inplace=True)
    plants.to_sql(name='plants',
                  con=engine, index=False, if_exists='append',
                  dtype={'id': Integer, 'name': String})

    utilities.rename(columns={'utility_id': 'id', 'utility_name': 'name'},
                     inplace=True)
    utilities.to_sql(name='utilities',
                     con=engine, index=False, if_exists='append',
                     dtype={'id': Integer, 'name': String})

    utilities_eia923.rename(columns={'operator_id_eia923': 'operator_id',
                                     'operator_name_eia923': 'operator_name',
                                     'utility_id': 'util_id_pudl'},
                            inplace=True)
    utilities_eia923.to_sql(name='utilities_eia923',
                            con=engine, index=False, if_exists='append',
                            dtype={'operator_id': Integer,
                                   'operator_name': String,
                                   'util_id_pudl': Integer})

    utilities_ferc1.rename(columns={'respondent_id_ferc1': 'respondent_id',
                                    'respondent_name_ferc1': 'respondent_name',
                                    'utility_id': 'util_id_pudl'},
                           inplace=True)
    utilities_ferc1.to_sql(name='utilities_ferc1',
                           con=engine, index=False, if_exists='append',
                           dtype={'respondent_id': Integer,
                                  'respondent_name': String,
                                  'util_id_pudl': Integer})

    plants_eia923.rename(columns={'plant_id_eia923': 'plant_id',
                                  'plant_name_eia923': 'plant_name',
                                  'plant_id': 'plant_id_pudl'},
                         inplace=True)
    plants_eia923.to_sql(name='plants_eia923',
                         con=engine, index=False, if_exists='append',
                         dtype={'plant_id': Integer,
                                'plant_name': String,
                                'plant_id_pudl': Integer})

    plants_ferc1.rename(columns={'respondent_id_ferc1': 'respondent_id',
                                 'plant_name_ferc1': 'plant_name',
                                 'plant_id': 'plant_id_pudl'},
                        inplace=True)
    plants_ferc1.to_sql(name='plants_ferc1',
                        con=engine, index=False, if_exists='append',
                        dtype={'respondent_id': Integer,
                               'plant_name': String,
                               'plant_id_pudl': Integer})

    utility_plant_assn.to_sql(name='util_plant_assn',
                              con=engine, index=False, if_exists='append',
                              dtype={'plant_id': Integer,
                                     'utility_id': Integer})


###############################################################################
###############################################################################
# BEGIN FERC 1 INGEST FUNCTIONS
###############################################################################
###############################################################################


def ingest_fuel_ferc1(pudl_engine, ferc1_engine, ferc1_years):
    """Clean & ingest f1_fuel table from FERC Form 1 DB into the PUDL DB."""
    # Grab the f1_fuel SQLAlchemy Table object from the metadata object.
    f1_fuel = ferc1_meta.tables['f1_fuel']
    # Generate a SELECT statement that pulls all fields of the f1_fuel table,
    # but only gets records with plant names, and non-zero fuel amounts:
    f1_fuel_select = select([f1_fuel]).\
        where(f1_fuel.c.fuel != '').\
        where(f1_fuel.c.fuel_quantity > 0).\
        where(f1_fuel.c.plant_name != '').\
        where(f1_fuel.c.report_year.in_(ferc1_years))
    # Use the above SELECT to pull those records into a DataFrame:
    ferc1_fuel_df = pd.read_sql(f1_fuel_select, ferc1_engine)

    # Discard DataFrame columns that we aren't pulling into PUDL:
    ferc1_fuel_df.drop(['spplmnt_num', 'row_number', 'row_seq', 'row_prvlg',
                        'report_prd'], axis=1, inplace=True)

    # Standardize plant_name capitalization and remove leading/trailing white
    # space -- necesary b/c plant_name is part of many foreign keys.
    ferc1_fuel_df['plant_name'] = ferc1_fuel_df['plant_name'].str.strip()
    ferc1_fuel_df['plant_name'] = ferc1_fuel_df['plant_name'].str.title()

    # Take the messy free-form fuel & fuel_unit fields, and do our best to
    # map them to some canonical categories... this is necessarily imperfect:
    ferc1_fuel_df.fuel = cleanstrings(ferc1_fuel_df.fuel,
                                      ferc1_fuel_strings,
                                      unmapped=np.nan)
    ferc1_fuel_df.fuel_unit = cleanstrings(ferc1_fuel_df.fuel_unit,
                                           ferc1_fuel_unit_strings,
                                           unmapped=np.nan)

    # Conver to MW/MWh units across the board.
    ferc1_fuel_df['fuel_cost_per_mwh'] = 1000 * ferc1_fuel_df['fuel_cost_kwh']
    ferc1_fuel_df.drop('fuel_cost_kwh', axis=1, inplace=True)
    ferc1_fuel_df['fuel_mmbtu_per_mwh'] = 1000 * \
        ferc1_fuel_df['fuel_generaton']
    ferc1_fuel_df.drop('fuel_generaton', axis=1, inplace=True)

    # Drop any records that are missing data. This is a blunt instrument, to
    # be sure. In some cases we lose data here, because some utilities have
    # (for example) a "Total" line w/ only fuel_mmbtu_per_kwh on it. Grr.
    ferc1_fuel_df.dropna(inplace=True)

    # Make sure that the DataFrame column names (which were imported from the
    # f1_fuel table) match their corresponding field names in the PUDL DB.
    ferc1_fuel_df.rename(columns={
        # FERC 1 DB Name      PUDL DB Name
        'fuel_quantity': 'fuel_qty_burned',
        'fuel_avg_heat': 'fuel_avg_mmbtu_per_unit',
        'fuel_cost_burned': 'fuel_cost_per_unit_burned',
        'fuel_cost_delvd': 'fuel_cost_per_unit_delivered',
                           'fuel_cost_btu': 'fuel_cost_per_mmbtu'},
                         inplace=True)
    ferc1_fuel_df.to_sql(name='fuel_ferc1',
                         con=pudl_engine, index=False, if_exists='append',
                         dtype={'respondent_id': Integer,
                                'report_year': Integer})


def ingest_plants_steam_ferc1(pudl_engine, ferc1_engine, ferc1_years):
    """Clean f1_steam table of the FERC Form 1 DB and pull into the PUDL DB."""
    f1_steam = ferc1_meta.tables['f1_steam']
    f1_steam_select = select([f1_steam]).\
        where(f1_steam.c.net_generation > 0).\
        where(f1_steam.c.plant_name != '').\
        where(f1_steam.c.report_year.in_(ferc1_years))

    ferc1_steam_df = pd.read_sql(f1_steam_select, ferc1_engine)
    # Discard DataFrame columns that we aren't pulling into PUDL:
    ferc1_steam_df.drop(['spplmnt_num', 'row_number', 'row_seq', 'row_prvlg',
                         'report_prd'], axis=1, inplace=True)

    # Standardize plant_name capitalization and remove leading/trailing white
    # space -- necesary b/c plant_name is part of many foreign keys.
    ferc1_steam_df['plant_name'] = ferc1_steam_df['plant_name'].str.strip()
    ferc1_steam_df['plant_name'] = ferc1_steam_df['plant_name'].str.title()

    # Take the messy free-form type_const and plant_kind fields, and do our
    # best to map them to some canonical categories...
    # this is necessarily imperfect:

    ferc1_steam_df.type_const = cleanstrings(ferc1_steam_df.type_const,
                                             ferc1_type_const_strings,
                                             unmapped=np.nan)
    ferc1_steam_df.plant_kind = cleanstrings(ferc1_steam_df.plant_kind,
                                             ferc1_plant_kind_strings,
                                             unmapped=np.nan)

    # Force the construction and installation years to be numeric values, and
    # set them to NA if they can't be converted. (table has some junk values)
    ferc1_steam_df['yr_const'] = pd.to_numeric(
        ferc1_steam_df['yr_const'],
        errors='coerce')
    ferc1_steam_df['yr_installed'] = pd.to_numeric(
        ferc1_steam_df['yr_installed'],
        errors='coerce')

    # Converting everything to per MW and MWh units...
    ferc1_steam_df['cost_per_mw'] = 1000 * ferc1_steam_df['cost_per_kw']
    ferc1_steam_df.drop('cost_per_kw', axis=1, inplace=True)
    ferc1_steam_df['net_generation_mwh'] = 1000 * \
        ferc1_steam_df['net_generation']
    ferc1_steam_df.drop('net_generation', axis=1, inplace=True)
    ferc1_steam_df['expns_per_mwh'] = 1000 * ferc1_steam_df['expns_kwh']
    ferc1_steam_df.drop('expns_kwh', axis=1, inplace=True)

    ferc1_steam_df.rename(columns={
        # FERC 1 DB Name      PUDL DB Name
        'yr_const': 'year_constructed',
        'yr_installed': 'year_installed',
        'tot_capacity': 'total_capacity_mw',
        'peak_demand': 'peak_demand_mw',
        'plnt_capability': 'plant_capability_mw',
        'when_limited': 'water_limited_mw',
        'when_not_limited': 'not_water_limited_mw',
        'avg_num_of_emp': 'avg_num_employees',
        'net_generation': 'net_generation_mwh',
        'cost_of_plant_to': 'cost_of_plant_total',
        'expns_steam_othr': 'expns_steam_other',
        'expns_engnr': 'expns_engineering',
        'tot_prdctn_expns': 'expns_production_total'},
        inplace=True)
    ferc1_steam_df.to_sql(name='plants_steam_ferc1',
                          con=pudl_engine, index=False, if_exists='append',
                          dtype={'respondent_id': Integer,
                                 'report_year': Integer,
                                 'type_const': String,
                                 'plant_kind': String,
                                 'year_constructed': Integer,
                                 'year_installed': Integer})


def ingest_plants_hydro_ferc1(pudl_engine, ferc1_engine, ferc1_years):
    """Ingest f1_hydro table of FERC Form 1 DB into PUDL DB."""
    f1_hydro = ferc1_meta.tables['f1_hydro']

    f1_hydro_select = select([f1_hydro]).\
        where(f1_hydro.c.plant_name != '').\
        where(f1_hydro.c.report_year.in_(ferc1_years))

    ferc1_hydro_df = pd.read_sql(f1_hydro_select, ferc1_engine)
    ferc1_hydro_df.drop(['spplmnt_num', 'row_number', 'row_seq', 'row_prvlg',
                         'report_prd'], axis=1, inplace=True)

    # Standardize plant_name capitalization and remove leading/trailing white
    # space -- necesary b/c plant_name is part of many foreign keys.
    ferc1_hydro_df['plant_name'] = ferc1_hydro_df['plant_name'].str.strip()
    ferc1_hydro_df['plant_name'] = ferc1_hydro_df['plant_name'].str.title()

    # Converting kWh to MWh
    ferc1_hydro_df['net_generation_mwh'] = \
        ferc1_hydro_df['net_generation'] / 1000.0
    ferc1_hydro_df.drop('net_generation', axis=1, inplace=True)
    # Converting cost per kW installed to cost per MW installed:
    ferc1_hydro_df['cost_per_mw'] = ferc1_hydro_df['cost_per_kw'] * 1000.0
    ferc1_hydro_df.drop('cost_per_kw', axis=1, inplace=True)
    # Converting kWh to MWh
    ferc1_hydro_df['expns_per_mwh'] = ferc1_hydro_df['expns_kwh'] * 1000.0
    ferc1_hydro_df.drop('expns_kwh', axis=1, inplace=True)

    ferc1_hydro_df['yr_const'] = pd.to_numeric(
        ferc1_hydro_df['yr_const'],
        errors='coerce')
    ferc1_hydro_df['yr_installed'] = pd.to_numeric(
        ferc1_hydro_df['yr_installed'],
        errors='coerce')
    ferc1_hydro_df.dropna(inplace=True)
    ferc1_hydro_df.rename(columns={
        # FERC1 DB          PUDL DB
        'project_no': 'project_number',
        'yr_const': 'year_constructed',
        'plant_const': 'plant_construction',
        'yr_installed': 'year_installed',
        'tot_capacity': 'total_capacity_mw',
        'peak_demand': 'peak_demand_mw',
        'plant_hours': 'plant_hours_connected_while_generating',
        'favorable_cond': 'net_capacity_favorable_conditions_mw',
        'adverse_cond': 'net_capacity_adverse_conditions_mw',
        'avg_num_of_emp': 'avg_number_employees',
        'cost_of_land': 'cost_land',
        'expns_engnr': 'expns_engineering',
        'expns_total': 'expns_production_total'
    }, inplace=True)

    ferc1_hydro_df.to_sql(name='plants_hydro_ferc1',
                          con=pudl_engine, index=False, if_exists='append',
                          dtype={'respondent_id': Integer,
                                 'report_year': Integer})


def ingest_plants_pumped_storage_ferc1(pudl_engine, ferc1_engine, ferc1_years):
    """Ingest f1_pumped_storage table of FERC Form 1 DB into PUDL DB."""
    f1_pumped_storage = ferc1_meta.tables['f1_pumped_storage']

    # Removing the empty records.
    # This reduces the entries for 2015 from 272 records to 27.
    f1_pumped_storage_select = select([f1_pumped_storage]).\
        where(f1_pumped_storage.c.plant_name != '').\
        where(f1_pumped_storage.c.report_year.in_(ferc1_years))

    ferc1_pumped_storage_df = pd.read_sql(
        f1_pumped_storage_select, ferc1_engine)
    ferc1_pumped_storage_df.drop(['spplmnt_num', 'row_number', 'row_seq',
                                  'row_prvlg', 'report_prd'],
                                 axis=1, inplace=True)

    # Standardize plant_name capitalization and remove leading/trailing white
    # space -- necesary b/c plant_name is part of many foreign keys.
    ferc1_pumped_storage_df['plant_name'] = \
        ferc1_pumped_storage_df['plant_name'].str.strip()
    ferc1_pumped_storage_df['plant_name'] = \
        ferc1_pumped_storage_df['plant_name'].str.title()

    # Converting kWh to MWh
    ferc1_pumped_storage_df['net_generation_mwh'] = \
        ferc1_pumped_storage_df['net_generation'] / 1000.0
    ferc1_pumped_storage_df.drop('net_generation', axis=1, inplace=True)

    ferc1_pumped_storage_df['energy_used_for_pumping_mwh'] = \
        ferc1_pumped_storage_df['energy_used'] / 1000.0
    ferc1_pumped_storage_df.drop(
        'energy_used_for_pumping_mwh', axis=1, inplace=True)

    ferc1_pumped_storage_df['net_load_mwh'] = \
        ferc1_pumped_storage_df['net_load'] / 1000.0
    ferc1_pumped_storage_df.drop('net_load_mwh', axis=1, inplace=True)

    # Converting cost per kW installed to cost per MW installed:
    ferc1_pumped_storage_df['cost_per_mw'] = \
        ferc1_pumped_storage_df['cost_per_kw'] * 1000.0
    ferc1_pumped_storage_df.drop('cost_per_mw', axis=1, inplace=True)

    ferc1_pumped_storage_df['expns_per_mwh'] = \
        ferc1_pumped_storage_df['expns_kwh'] * 1000.0
    ferc1_pumped_storage_df.drop('expns_per_mwh', axis=1, inplace=True)

    ferc1_pumped_storage_df.dropna(inplace=True)

    ferc1_pumped_storage_df.rename(columns={
        # FERC1 DB          PUDL DB
        'respondent_id': 'id',
        'report_year ': 'year',
        'project_no': 'project_number',
        'tot_capacity': 'total_capacity_mw',
        'peak_demand': 'peak_demand_mw',
        'plant_hours': 'plant_hours_connected_while_generating',
        'plant_capability': 'plant_capability_mw',
        'avg_num_of_emp': 'avg_number_employees',
        'net_generation': 'net_generation_mwh',
        'net_load': 'net_load_mwh',
        'cost_wheels': 'cost_wheels_turbines_generators',
        'cost_electric': 'cost_equipment',
        'cost_misc_eqpmnt': 'cost_equipment_misc',
        'cost_of_plant': 'cost_plant_total',
        'cost_per_kw': 'cost_per_mw',
        'expns_water_pwr': 'expns_water_for_pwr',
        'expns_pump_stg': 'expns_pump_storage',
        'expns_misc_power': 'expns_generation_misc',
        'expns_misc_plnt': 'expns_misc_plant',
        'expns_producton': 'expns_producton_before_pumping',
        'tot_prdctn_exns': 'expns_producton_total',
        'expns_kwh': 'expns_per_mwh'})

    ferc1_pumped_storage_df.to_sql(name='plants_pumped_storage_ferc1',
                                   con=pudl_engine, index=False,
                                   if_exists='append')


def ingest_accumulated_depreciation_ferc1(pudl_engine,
                                          ferc1_engine,
                                          ferc1_years):
    """Ingest f1_accumdepr_prvs table from FERC Form 1 DB."""
    f1_accumdepr_prvsn = ferc1_meta.tables['f1_accumdepr_prvsn']
    f1_accumdepr_prvsn_select = select([f1_accumdepr_prvsn]).\
        where(f1_accumdepr_prvsn.c.report_year.in_(ferc1_years))

    ferc1_apd_df = pd.read_sql(f1_accumdepr_prvsn_select, ferc1_engine)

    # Discard DataFrame columns that we aren't pulling into PUDL. For
    ferc1_apd_df.drop(['spplmnt_num', 'row_seq',
                       'row_prvlg', 'item', 'report_prd'],
                      axis=1, inplace=True)

    ferc1_acct_apd = ferc_accumulated_depreciation.drop(
        ['ferc_account_description'], axis=1)
    ferc1_acct_apd.dropna(inplace=True)
    ferc1_acct_apd['row_number'] = ferc1_acct_apd['row_number'].astype(int)

    ferc1_accumdepr_prvsn_df = pd.merge(ferc1_apd_df, ferc1_acct_apd,
                                        how='left', on='row_number')
    ferc1_accumdepr_prvsn_df.drop('row_number', axis=1, inplace=True)

    ferc1_accumdepr_prvsn_df.\
        to_sql(name='accumulated_depreciation_ferc1',
               con=pudl_engine, index=False, if_exists='append',
               dtype={'respondent_id': Integer,
                      'report_year': Integer,
                      'line_id': String,
                      'total_cde': Numeric(14, 2),
                      'electric_plant': Numeric(14, 2),
                      'future_plant': Numeric(14, 2),
                      'leased plant': Numeric(14, 2)})


def ingest_plant_in_service_ferc1(pudl_engine, ferc1_engine, ferc1_years):
    """Ingest f1_plant_in_srvce table of FERC Form 1 DB into PUDL DB."""
    f1_plant_in_srvce = ferc1_meta.tables['f1_plant_in_srvce']
    f1_plant_in_srvce_select = select([f1_plant_in_srvce]).\
        where(f1_plant_in_srvce.c.report_year.in_(ferc1_years))

    ferc1_pis_df = pd.read_sql(f1_plant_in_srvce_select, ferc1_engine)

    # Discard DataFrame columns that we aren't pulling into PUDL. For the
    # Plant In Service table, we need to hold on to the row_number because it
    # corresponds to a FERC account number.
    ferc1_pis_df.drop(['spplmnt_num', 'row_seq', 'row_prvlg', 'report_prd'],
                      axis=1, inplace=True)

    # Now we need to add a column to the DataFrame that has the FERC account
    # IDs corresponding to the row_number that's already in there...
    ferc_accts_df = ferc_electric_plant_accounts.drop(
        ['ferc_account_description'], axis=1)
    ferc_accts_df.dropna(inplace=True)
    ferc_accts_df['row_number'] = ferc_accts_df['row_number'].astype(int)

    ferc1_pis_df = pd.merge(ferc1_pis_df, ferc_accts_df,
                            how='left', on='row_number')
    ferc1_pis_df.drop('row_number', axis=1, inplace=True)

    ferc1_pis_df.rename(columns={
        # FERC 1 DB Name  PUDL DB Name
        'begin_yr_bal': 'beginning_year_balance',
        'addition': 'additions',
        'yr_end_bal': 'year_end_balance'},
        inplace=True)
    ferc1_pis_df.to_sql(name='plant_in_service_ferc1',
                        con=pudl_engine, index=False, if_exists='append',
                        dtype={'respondent_id': Integer,
                               'report_year': Integer,
                               'ferc_account_id': String,
                               'beginning_year_balance': Numeric(14, 2),
                               'additions': Numeric(14, 2),
                               'retirements': Numeric(14, 2),
                               'adjustments': Numeric(14, 2),
                               'transfers': Numeric(14, 2),
                               'year_end_balance': Numeric(14, 2)})


def ingest_plants_small_ferc1(pudl_engine, ferc1_engine, ferc1_years):
    """
    Ingest f1_gnrt_plant table of FERC Form 1 DB into PUDL DB.

    Zane Selvans is doing this one. NOT DONE YET.
    """
    f1_small_table = ferc1_meta.tables['f1_gnrt_plant']
    f1_small_select = select([f1_small_table, ]).\
        where(f1_gnrt_plant.c.report_year.in_(ferc1_years))
    ferc1_small_df = pd.read_sql(f1_small_select, ferc1_engine)

    # In the FERC1 small plants data there are many lists of plants of a
    # particular type (e.g. wind, hydro) where the only indicator of the type
    # of plant is the HEADing at the beginning of the list, so we're going to
    # need row & supplement numbers to parse out the beginning of the lists...
    ferc1_small_df.drop(['row_seq', 'row_prvlg', 'report_prd'],
                        axis=1, inplace=True)

    # Standardize plant_name capitalization and remove leading/trailing white
    # space -- necesary b/c plant_name is part of many foreign keys.
    ferc1_small_df['plant_name'] = ferc1_small_df['plant_name'].str.strip()
    ferc1_small_df['plant_name'] = ferc1_small_df['plant_name'].str.title()

    # Clean up the fuel strings using the combined fuel strings dictionries
    ferc1_small_df.kind_of_fuel = cleanstrings(ferc1_small_df.kind_of_fuel,
                                               ferc1_fuel_strings,
                                               unmapped=np.nan)

    # Force the construction and installation years to be numeric values, and
    # set them to NA if they can't be converted. (table has some junk values)
    ferc1_small_df['yr_constructed'] = pd.to_numeric(
        ferc1_small_df['yr_constructed'],
        errors='coerce')
    # Convert from cents per mmbtu to dollars per mmbtu to be consistent
    # with the f1_fuel table data. Also, let's use a clearer name.
    ferc1_small_df['fuel_cost_per_mmbtu'] = ferc1_small_df['fuel_cost'] / 100.0
    ferc1_small_df.drop('fuel_cost', axis=1, inplace=True)

    # PARSE OUT PLANT TYPE BASED ON EMBEDDED TITLES HERE...

    # Create a single "record number" for the individual lines in the FERC
    # Form 1 that report different small plants, so that we can more easily
    # tell whether they are adjacent to each other in the reporting.
    ferc1_small_df['record_number'] = 46 * ferc1_small_df['spplmnt_num'] + \
        ferc1_small_df['row_number']
    ferc1_small_df.drop(['row_number', 'spplmnt_num'], axis=1, inplace=True)

    ferc1_small_df.rename(columns={
        # FERC 1 DB Name      PUDL DB Name
        'yr_constructed': 'year_constructed',
        'capacity_rating': 'total_capacity',
        'net_demand': 'peak_demand_mw',
        'net_generation': 'net_generation_mwh',
        'plant_cost': 'cost_of_plant_total',
        'plant_cost_mw': 'cost_of_plant_per_mw',
        'operation': 'cost_of_operation',
        'expns_maint': 'expns_maintenance',
        'fuel_cost': 'fuel_cost_per_mmbtu'},
        inplace=True)
    ferc1_small_df.to_sql(name='plants_small_ferc1',
                          con=pudl_engine, index=False, if_exists='append',
                          dtype={'respondent_id': Integer,
                                 'report_year': Integer,
                                 'plant_name': String,
                                 'kind_of_fuel': String,
                                 'year_constructed': Integer})


def ingest_purchased_power_ferc1(pudl_engine, ferc1_engine, ferc1_years):
    """Ingest f1_plant_in_srvce table of FERC Form 1 DB into PUDL DB."""
    f1_purchased_pwr = ferc1_meta.tables['f1_purchased_pwr']
    f1_purchased_pwr_select = select([f1_purchased_pwr]).\
        where(f1_purchased_pwr.c.report_year.in_(ferc1_years))

    ferc1_purchased_pwr_df = pd.read_sql(f1_purchased_pwr_select, ferc1_engine)

    ferc1_purchased_pwr_df.drop(['spplmnt_num', 'row_number', 'row_seq',
                                 'row_prvlg', 'report_prd'],
                                axis=1, inplace=True)
    ferc1_purchased_pwr_df.replace(to_replace='', value=np.nan, inplace=True)
    ferc1_purchased_pwr_df.dropna(subset=['sttstcl_clssfctn',
                                          'rtsched_trffnbr'], inplace=True)

    ferc1_purchased_pwr_df.rename(columns={
        # FERC 1 DB Name  PUDL DB Name
        'athrty_co_name': 'authority_company_name',
        'sttstcl_clssfctn': 'statistical_classification',
        'rtsched_trffnbr': 'rate_schedule_tariff_number',
        'avgmth_bill_dmnd': 'average_billing_demand',
        'avgmth_ncp_dmnd': 'average_monthly_ncp_demand',
        'avgmth_cp_dmnd': 'average_monthly_cp_demand',
        'mwh_recv': 'mwh_received',
        'mwh_delvd': 'mwh_delivered',
        'dmnd_charges': 'demand_charges',
        'erg_charges': 'energy_charges',
        'othr_charges': 'other_charges',
        'settlement_tot': 'settlement_total'},
        inplace=True)

    ferc1_purchased_pwr_df.to_sql(name='purchased_power_ferc1',
                                  con=pudl_engine, index=False,
                                  if_exists='append',
                                  dtype={'respondent_id': Integer,
                                         'report_year': Integer,
                                         'authority_company_name': String,
                                         'statistical_classification': String,
                                         'rate_schedule_tariff_number': String,
                                         'average_billing_demand': String,
                                         'average_monthly_ncp_demand': String,
                                         'average_monthly_cp_demand': String,
                                         'mwh_purchased': Numeric(14, 2),
                                         'mwh_received': Numeric(14, 2),
                                         'mwh_delivered': Numeric(14, 2),
                                         'demand_charges': Numeric(14, 2),
                                         'energy_charges': Numeric(14, 2),
                                         'other_charges': Numeric(14, 2),
                                         'settlement_total': Numeric(14, 2)})

###############################################################################
###############################################################################
# BEGIN EIA923 INGEST FUNCTIONS
###############################################################################
###############################################################################


def ingest_plant_info_eia923(pudl_engine, eia923_dfs):
    """
    Ingest data describing static attributes of plants from EIA Form 923.

    Much of the static plant information is reported repeatedly, and scattered
    across several different pages of EIA 923. This function tries to bring it
    together into one unified, unduplicated table.
    """
    # From 'plant_frame'
    plant_frame_cols = ['plant_id',
                        'plant_state',
                        'combined_heat_and_power_status',
                        'sector_number',
                        'naics_code',
                        'reporting_frequency']

    plant_frame_df = eia923_dfs['plant_frame'][plant_frame_cols]

    # From 'generation_fuel' to merge by plant_id
    gen_fuel_cols = ['plant_id',
                     'census_region',
                     'nerc_region']

    gen_fuel_df = eia923_dfs['generation_fuel'][gen_fuel_cols]

    # Remove "State fuel-level increment" records... which don't pertain to
    # any particular plant (they have plant_id == operator_id == 99999)
    gen_fuel_df = gen_fuel_df[gen_fuel_df.plant_id != 99999]

    # because there ought to be one entry for each plant in each year's worth
    # of data, we're dropping duplicates by plant_id in the two data frames
    # which we're combining. TODO: populate a table that lists plant operators
    # by year... nominally plant_ownership_eia923
    plant_info_df = pd.merge(plant_frame_df.drop_duplicates('plant_id'),
                             gen_fuel_df.drop_duplicates('plant_id'),
                             how='outer', on='plant_id')

    # Since this is a plain Yes/No variable -- just make it a real Boolean.
    plant_info_df.combined_heat_and_power_status.replace(
        {'N': False, 'Y': True}, inplace=True)

    plant_info_df.rename(columns={
        # column HEADing in EIA 923        PUDL DB field name
        'combined_heat_and_power_status': 'combined_heat_power',
        'sector_number': 'eia_sector'},
        inplace=True)
    # Output into the DB:
    plant_info_df.to_sql(name='plant_info_eia923',
                         con=pudl_engine, index=False, if_exists='append',
                         dtype={'eia_sector': Integer,
                                'naics_code': Integer,
                                'combined_heat_power': Boolean})


def ingest_generation_fuel_eia923(pudl_engine, eia923_dfs):
    """
    Ingest generation and fuel data from Page 1 of EIA Form 923 into PUDL DB.

    Page 1 of EIA 923 (in recent years) reports generation and fuel consumption
    on a monthly, per-plant basis.
    """
    # This needs to be a copy of what we're passed in so we can edit it.
    gf_df = eia923_dfs['generation_fuel'].copy()

    # Drop fields we're not inserting into the generation_fuel_eia923 table.
    cols_to_drop = ['combined_heat_and_power_plant',
                    'plant_name',
                    'operator_name',
                    'operator_id',
                    'plant_state',
                    'census_region',
                    'nerc_region',
                    'naics_code',
                    'eia_sector_number',
                    'sector_name',
                    'physical_unit_label',
                    'total_fuel_consumption_quantity',
                    'electric_fuel_consumption_quantity',
                    'total_fuel_consumption_mmbtu',
                    'elec_fuel_consumption_mmbtu',
                    'net_generation_megawatthours']
    gf_df.drop(cols_to_drop, axis=1, inplace=True)

    # Convert the EIA923 DataFrame from yearly to monthly records.
    gf_df = yearly_to_monthly_eia923(gf_df, month_dict_2015_eia923)
    # Replace the EIA923 NA value ('.') with a real NA value.
    gf_df.replace(to_replace='^\.$', value=np.nan, regex=True, inplace=True)
    # Remove "State fuel-level increment" records... which don't pertain to
    # any particular plant (they have plant_id == operator_id == 99999)
    gf_df = gf_df[gf_df.plant_id != 99999]

    # Rename them to be consistent with the PUDL DB fields, if need be.
    gf_df.rename(columns={
        # EIA 923              PUDL DB field name
        'reported_prime_mover': 'prime_mover',
        'reported_fuel_type_code': 'fuel_type',
        'aer_fuel_type_code': 'aer_fuel_type',
        'quantity': 'fuel_consumed_total',
        'elec_quantity': 'fuel_consumed_for_electricity',
        'mmbtuper_unit': 'fuel_mmbtu_per_unit',
        'tot_mmbtu': 'fuel_consumed_total_mmbtu',
        'elec_mmbtu': 'fuel_consumed_for_electricity_mmbtu',
        'netgen': 'net_generation_mwh'},
        inplace=True)

    gf_df.to_sql(name='generation_fuel_eia923',
                 con=pudl_engine, index=False, if_exists='append',
                 dtype={'plant_id': Integer,
                        'nuclear_unit_id': Integer,
                        'prime_mover': String,
                        'fuel_type': String,
                        'aer_fuel_type': String,
                        'fuel_consumed_total': Float,
                        'fuel_consumed_for_electricity': Float,
                        'fuel_mmbtu_per_unit': Float,
                        'fuel_consumed_total_mmbtu': Float,
                        'fuel_consumed_for_electricity_mmbtu': Float,
                        'net_generation_mwh': Float},
                 chunksize=1000)

"""
 def ingest_operator_info_eia923(pudl_engine, eia923_dfs):
        # Ingest data on static attributes of operators from EIA Form 923.
        # operator_id
        # operator_name
        # regulatory_status: make this a Boolean:
        #  - Regulated = True
        #  - Unregulated = False
        # From 'fuel_receipts_costs'
        fuel_receipts_costs_cols = ['operator_id', 'regulated']

        operator_df = eia923_dfs['fuel_receipts_costs'][fuel_receipts_costs_cols]

        # Since this is a plain Yes/No variable -- just make it a real Boolean.
        operator_df.regulated.replace(
            {'REG': True, 'UNR': False}, inplace=True)

        operator_df.to_sql(name='operator_info_eia923',
                       con=pudl_engine, index=False, if_exists='append',
                       dtype={'operator_id': Integer,
                              'regulated': Boolean}) """


def ingest_boiler_fuel_eia923(pudl_engine, eia923_dfs):
    """
    Ingest data on fuel consumption by boiler from EIA Form 923.

    This is going to populate boilers_eia923 and boiler_fuel_eia923 tables
    """
    # Populate 'boilers_eia923' table
    boiler_cols = ['plant_id',
                   'boiler_id',
                   'reported_prime_mover']

    boilers_df = eia923_dfs['boiler_fuel'][boiler_cols]
    boilers_df = boilers_df.drop_duplicates(
        subset=['plant_id', 'boiler_id'])

    boilers_df.rename(columns={
        # column HEADing in EIA 923        PUDL DB field name
        'reported_prime_mover': 'prime_mover'},
        inplace=True)

    # drop null values from foreign key fields
    boilers_df.dropna(subset=['boiler_id', 'plant_id'], inplace=True)

    boilers_df.to_sql(name='boilers_eia923',
                      con=pudl_engine, index=False, if_exists='append',
                      dtype={'plant_id': Integer,
                             'boiler_id': String,
                             'prime_mover': String})

    # Populate 'boiler_fuel_eia923' table
    # This needs to be a copy of what we're passed in so we can edit it.
    bf_df = eia923_dfs['boiler_fuel'].copy()

    # Drop fields we're not inserting into the boiler_fuel_eia923 table.
    cols_to_drop = ['combined_heat_and_power_plant',
                    'plant_name',
                    'operator_name',
                    'operator_id',
                    'plant_state',
                    'census_region',
                    'nerc_region',
                    'naics_code',
                    'sector_number',
                    'sector_name',
                    'physical_unit_label',
                    'total_fuel_consumption_quantity']
    bf_df.drop(cols_to_drop, axis=1, inplace=True)

    bf_df.dropna(subset=['boiler_id', 'plant_id'], inplace=True)

    # Convert the EIA923 DataFrame from yearly to monthly records.
    bf_df = yearly_to_monthly_eia923(bf_df, month_dict_2015_eia923)
    # Replace the EIA923 NA value ('.') with a real NA value.
    bf_df.replace(to_replace='^\.$', value=np.nan, regex=True, inplace=True)
    # Remove "State fuel-level increment" records... which don't pertain to
    # any particular plant (they have plant_id == operator_id == 99999)
    # These don't occur in boiler_fuel tab so should be able to leave this out
    # bf_df = bf_df[bf_df.plant_id != 99999]

    # Rename them to be consistent with the PUDL DB fields, if need be.
    bf_df.rename(columns={
        # EIA 923              PUDL DB field name
        'reported_prime_mover': 'prime_mover',
        'reported_fuel_type_code': 'fuel_type',
        'quantity_of_fuel_consumed': 'fuel_qty_consumed',
        'mmbtu_per_unit': 'fuel_mmbtu_per_unit'},
        inplace=True)

    bf_df.to_sql(name='boiler_fuel_eia923',
                 con=pudl_engine, index=False, if_exists='append',
                 dtype={'plant_id': Integer,
                        'boiler_id': String,
                        'prime_mover': String,
                        'fuel_type': String,
                        'fuel_consumed_total': Float,
                        'fuel_mmbtu_per_unit': Float,
                        'sulfur_content': Float,
                        'ash_content': Float},
                 chunksize=1000)


def ingest_generator_eia923(pudl_engine, eia923_dfs):
    """Ingest data on electricity production by generator from EIA Form 923."""
    # This needs to be a copy of what we're passed in so we can edit it.
    g_df = eia923_dfs['generator'].copy()

    # Populating the 'generators_eia923' table
    generator_cols = ['plant_id',
                      'generator_id',
                      'reported_prime_mover']

    generators_df = eia923_dfs['generator'][generator_cols]
    generators_df = generators_df.drop_duplicates(
        subset=['plant_id', 'generator_id'])

    generators_df.rename(columns={
        # column HEADing in EIA 923        PUDL DB field name
        'reported_prime_mover': 'prime_mover'},
        inplace=True)

    # drop null values from foreign key fields
    generators_df.dropna(subset=['generator_id', 'plant_id'], inplace=True)

    generators_df.to_sql(name='generators_eia923',
                         con=pudl_engine, index=False, if_exists='append',
                         dtype={'plant_id': Integer,
                                'generator_id': String,
                                'prime_mover': String})

    # Populating the generation_eia923 table:
    # This needs to be a copy of what we're passed in so we can edit it.
    g_df = eia923_dfs['generator'].copy()

    # Drop fields we're not inserting into the generation_eia923_fuel_eia923
    # table.
    cols_to_drop = ['combined_heat_and_power_plant',
                    'plant_name',
                    'operator_name',
                    'operator_id',
                    'plant_state',
                    'census_region',
                    'nerc_region',
                    'naics_code',
                    'sector_number',
                    'sector_name',
                    'net_generation_year_to_date']

    g_df.drop(cols_to_drop, axis=1, inplace=True)

    # Convert the EIA923 DataFrame from yearly to monthly records.
    g_df = yearly_to_monthly_eia923(g_df, month_dict_2015_eia923)
    # Replace the EIA923 NA value ('.') with a real NA value.
    g_df.replace(to_replace='^\.$', value=np.nan, regex=True, inplace=True)
    # Remove "State fuel-level increment" records... which don't pertain to
    # any particular plant (they have plant_id == operator_id == 99999)
    # These don't occur in boiler_fuel tab, so should be able to leave this out
    # g_df = g_df[g_df.plant_id != 99999]
    #
    # # Rename them to be consistent with the PUDL DB fields, if need be.
    g_df.rename(columns={
        # EIA 923              PUDL DB field name
        'reported_prime_mover': 'prime_mover',
        'net_generation': 'net_generation_mwh'},
        inplace=True)

    g_df.to_sql(name='generation_eia923',
                con=pudl_engine, index=False, if_exists='append',
                dtype={'plant_id': Integer,
                       'generator_id': String,
                       'prime_mover': String,
                       'net_generation_mwh': Float},
                chunksize=1000)


# fuel_receipts_cost ingest function
def ingest_fuel_receipts_costs_eia923(pudl_engine, eia923_dfs):
    """Ingest data on fuel purchases and costs from EIA Form 923."""
    #

    # Populate 'coalmine_info_eia923' table
    coalmine_cols = ['coalmine_name',
                     'coalmine_type',
                     'coalmine_state',
                     'coalmine_county',
                     'coalmine_msha_id']

    coalmine_df = eia923_dfs['fuel_receipts_costs'][coalmine_cols]
    # TODO: Not sure which fields of duplicates need to be dropped here
    # coalmine_df = coalmine_df.drop_duplicates(
    #     subset=['', ''])
    #
    # coalmine_df.rename(columns={
    #     # column HEADing in EIA 923        PUDL DB field name
    #     'reported_prime_mover': 'prime_mover'},
    #     inplace=True)

    # drop null values from foreign key fields
    #   coalmine_df.dropna(subset=['coalmine_name'], inplace=True)

    coalmine_df.to_sql(name='coalmine_info_eia923',
                       con=pudl_engine, index=False, if_exists='append',
                       dtype={'coalmine_name': String,
                              'coalmine_type': String,
                              'coalmine_state': String,
                              'coalmine_county': String,
                              'coalmine_msha_id': String},
                       chunksize=1000)

    frc_df = eia923_dfs['fuel_receipts_costs'].copy()

    # Drop fields we're not inserting into the fuel_receipts_costs_eia923
    # table.
    # TODO: For now, keeping coalmine_msha_id in here, but need to replace with
    # surrogate key
    cols_to_drop = ['plant_name',
                    'plant_state',
                    'operator_name',
                    'operator_id',
                    'fuel_group',
                    'coalmine_name',
                    'coalmine_type',
                    'coalmine_state',
                    'coalmine_county',
                    'regulated',
                    'reporting_frequency']

    frc_df.drop(cols_to_drop, axis=1, inplace=True)
    frc_df = frc_df[frc_df.plant_id != 8899]

# Convert the EIA923 DataFrame from yearly to monthly records.
# frc_df = yearly_to_monthly_eia923(frc_df, month_dict_2015_eia923)
# Replace the EIA923 NA value ('.') with a real NA value.
    frc_df.replace(to_replace='^\.$', value=np.nan, regex=True, inplace=True)

    # Rename them to be consistent with the PUDL DB fields, if need be.

    frc_df.rename(columns={
        # EIA 923              PUDL DB field name
        'purchase_type': 'contract_type',
        'reported_prime_mover': 'prime_mover',
        'quantity': 'qty',
        'natural_gas_transportation_service': 'natural_gas_transport'
    },
        inplace=True)

    frc_df.to_sql(name='fuel_receipts_costs_eia923',
                  con=pudl_engine, index=False, if_exists='append',
                  dtype={'plant_id': Integer,
                         'contract_type': String,
                         'contract_expiration_date': Integer,
                         'energy_source': String,
                         'coalmine_msha_id': Integer,
                         'supplier': String,
                         'qty': Integer,
                         'average_heat_content': Integer,
                         'average_sulfur_content': Integer,
                         'average_ash_content': Integer,
                         'average_mercury_content': Integer,
                         'fuel_cost': Float,
                         'primary_transportation_mode': String,
                         'secondary_transportation_mode': String,
                         'natural_gas_transport': String
                         },
                  chunksize=1000)


def ingest_stocks_eia923(pudl_engine, eia923_dfs):
    """Ingest data on fuel stocks from EIA Form 923."""
    pass


###############################################################################
###############################################################################
# BEGIN DATABASE INITIALIZATION
###############################################################################
###############################################################################


def init_db(ferc1_tables=ferc1_pudl_tables,
            ferc1_years=[2015, ],
            eia923_tables=eia923_pudl_tables,
            eia923_years=[2014, 2015, 2016],
            verbose=True, debug=False, testing=False):
    """
    Create the PUDL database and fill it up with data.

    ferc1_tables is a list of tables that will be created and ingested.
    By default only known to be working tables are ingested. That list of
    tables is defined in pudl.constants.

    You can tell it to ingest whatever list of tables you want, but if
    it's not in the list of known to be working tables, you need to set
    debug=True (otherwise it won't let you)
    """
    # Make sure that the tables we're being asked to ingest can actually be
    # pulled into both the FERC Form 1 DB, and the PUDL DB...
    if not debug:
        for table in ferc1_tables:
            assert(table in ferc1_working_tables)
            assert(table in ferc1_pudl_tables)

    if not debug:
        for table in eia923_tables:
            assert(table in eia923_pudl_tables)

    # Connect to the PUDL DB, wipe out & re-create tables:
    pudl_engine = db_connect_pudl(testing=testing)
    drop_tables_pudl(pudl_engine)
    create_tables_pudl(pudl_engine)
    # Populate all the static tables:
    if verbose:
        print("Ingesting static PUDL tables...")
    ingest_static_tables(pudl_engine)
    # Populate tables that relate FERC1 & EIA923 data to each other.
    if verbose:
        print("Sniffing EIA923/FERC1 glue tables...")
    ingest_glue_tables(pudl_engine)

    # BEGIN INGESTING FERC FORM 1 DATA:
    ferc1_ingest_functions = {
        'f1_fuel': ingest_fuel_ferc1,
        'f1_steam': ingest_plants_steam_ferc1,
        'f1_gnrt_plant': ingest_plants_small_ferc1,
        'f1_hydro': ingest_plants_hydro_ferc1,
        'f1_pumped_storage': ingest_plants_pumped_storage_ferc1,
        'f1_plant_in_srvce': ingest_plant_in_service_ferc1,
        'f1_purchased_pwr': ingest_purchased_power_ferc1,
        'f1_accumdepr_prvsn': ingest_accumulated_depreciation_ferc1}

    ferc1_engine = db_connect_ferc1(testing=testing)
    for table in ferc1_ingest_functions.keys():
        if table in ferc1_tables:
            if verbose:
                print("Ingesting {} from FERC Form 1 into PUDL.".format(table))
            ferc1_ingest_functions[table](pudl_engine,
                                          ferc1_engine,
                                          ferc1_years)

    # Because we're going to be combining data froms several different EIA923
    # spreadsheet pages into individual database tables, and it's time
    # consuming to read them in multiple times, let's try and read them all
    # into memory just once. In the long run this may not scale up.
    eia923_dfs = {}

# Let's selectively read in only the pages of EIA923 that we need in order
# to populate the tables we're initiliazing:
    if 'plant_info_eia923' in eia923_tables:
        for page in ['plant_frame', 'generation_fuel']:
            eia923_dfs[page] = get_eia923_page(page,
                                               years=eia923_years,
                                               verbose=verbose)
    if ('generation_fuel_eia923' in eia923_tables) \
            and ('generation_fuel' not in eia923_dfs.keys()):
        eia923_dfs['generation_fuel'] = get_eia923_page('generation_fuel',
                                                        years=eia923_years,
                                                        verbose=verbose)

    if 'fuel_stocks_eia923' in eia923_tables:
        pass  # no DB table defined for fuel stocks yet.

    if 'boiler_fuel_eia923' in eia923_tables:
        eia923_dfs['boiler_fuel'] = get_eia923_page('boiler_fuel',
                                                    years=eia923_years,
                                                    verbose=verbose)
    if 'generation_eia923' in eia923_tables:
        eia923_dfs['generator'] = get_eia923_page('generator',
                                                  years=eia923_years,
                                                  verbose=verbose)
    if 'fuel_receipts_costs_eia923' in eia923_tables:
        eia923_dfs['fuel_receipts_costs'] = \
            get_eia923_page('fuel_receipts_costs',
                            years=eia923_years,
                            verbose=verbose)

    # NOW START INGESTING EIA923 DATA:
    eia923_ingest_functions = {
        'plant_info_eia923': ingest_plant_info_eia923,
        'generation_fuel_eia923': ingest_generation_fuel_eia923,
        'boiler_fuel_eia923': ingest_boiler_fuel_eia923,
        'generation_eia923': ingest_generator_eia923,
        'fuel_receipts_costs_eia923': ingest_fuel_receipts_costs_eia923,
        'stocks_eia923': ingest_stocks_eia923
    #    'operator_info_eia923': ingest_operator_info_eia923
    }

    for table in eia923_ingest_functions.keys():
        if table in eia923_tables:
            if verbose:
                print("Ingesting {} from EIA 923 into PUDL.".format(table))
            eia923_ingest_functions[table](pudl_engine, eia923_dfs)
