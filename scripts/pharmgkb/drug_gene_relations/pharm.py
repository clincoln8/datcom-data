# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Generate instance mcf from PharmGKB files related to drug-gene associations.

 The PharmGKB files (drugs.tsv, chemicals.tsv, genes.tsv, relationships.tsv) are
 automatically downloaded and read in as pandas dataframes. Entities from
 drugs.tsv and chemicals.tsv are both referred to as drugs, unless otherwise
 indicated throughout this file. In order to get the Data Commons dcids for the
 drugs, the files from ./conversion are used to map PharmGKB ID, PubChem
 Compound ID, and InChI to ChEMBL IDs. Gene dcids are created by prepending the
 gene symbol with 'bio/hg19' and 'bio/hg38'.

Usage:
    $python3 pharm.py
"""
from sys import path
import zipfile
import io
import requests
import pandas as pd

import config

path.insert(1, '../../../')
# from Data Commons util folder
from util import mcf_template_filler


def download_pharmgkb_datasets():
    """Downloads dataset files from PharmGKB.

    Downloads chemicals.zip, drugs.zip, genes.zip, and relationships.zip to
    ./raw_data/<zip_file_name>/ . Each zipfile contains a tsv file of the
    necessary data, along with a README, and License, Creation, and Version
    information files.
    """
    urls = {
        'chemicals':
            'https://api.pharmgkb.org/v1/download/file/data/chemicals.zip',
        'drugs':
            'https://api.pharmgkb.org/v1/download/file/data/drugs.zip',
        'genes':
            'https://api.pharmgkb.org/v1/download/file/data/genes.zip',
        'relationships':
            'https://api.pharmgkb.org/v1/download/file/data/relationships.zip',
    }
    for zip_dir, url in urls.items():
        download = requests.get(url)
        files = zipfile.ZipFile(io.BytesIO(download.content))
        files.extractall('./raw_data/' + zip_dir)


def merge_chembls(chembl1, chembl2, chembl3):
    """Return single Chembl ID from the three chembl ids given.

    Args:
        chembl1: chembl id based on PharmGK ID
        chembl2: chembl id based on PubChem Compound id
        chembl3: chembl id based on InChI

    Returns:
        A single ChEMBL ID based on the the three given ids. Chembl retreived
        from pharmgkb has priorty, then pubchem Cid, then by inchi.
    """
    if not pd.isnull(chembl1) and chembl1:
        return chembl1
    if not pd.isnull(chembl2) and chembl2:
        return chembl2
    if not pd.isnull(chembl3) and chembl3:
        return chembl3
    return None


def append_chembls(combined_df):
    """Appends 'Chembl ID' and 'InChI Key' to a copy of given pandas dataframe.

    The conversion files from ./conversion are read in and a new chembl id
    column is appended for each file. Then the three columns are combined into
    'Chembl ID' by calling merge_chembls(). 'Chembl1' is based on the PharmGKB
    ID, 'Chembl2' is based on the PubChem Compound ID, 'Chembl3' is based on
    InChI/InChI Key.

    Args:
        df: combined drugs and chemical dataframe containing PharmGKB

    Returns:
        Copy of the given dataframe with the 'Chembl ID' and 'InChI Key' columns
        appended, along with the extra 'Chembl1','Chembl2', and 'Chembl3'
        columns.
    """

    drugs_df = combined_df.copy(deep=True)
    # read in chembl id based off of pharmgkb id
    pharm_chembl_df = pd.read_csv(
        './conversion/pharm_id_to_chembl_combined.csv')
    pharm_to_chembl_dict = pd.Series(
        pharm_chembl_df['ChEMBL ID'].values,
        index=pharm_chembl_df['PharmGKB ID']).to_dict()

    drugs_df['Chembl1'] = [
        pharm_to_chembl_dict[pharm_id]
        if pharm_id in pharm_to_chembl_dict else ''
        for pharm_id in drugs_df['PharmGKB Accession Id']
    ]

    # read in chembl based off of pubchem compound id
    pubchem_chembl_df = pd.read_csv(
        './conversion/pubchem_id_to_chembl_combined.csv')
    pubchem_to_chembl_dict = pd.Series(
        pubchem_chembl_df['ChEMBL ID'].values,
        index=pubchem_chembl_df['PubChem ID']).to_dict()

    drugs_df['Chembl2'] = [
        pubchem_to_chembl_dict[pubchem_id]
        if pubchem_id in pubchem_to_chembl_dict else ''
        for pubchem_id in drugs_df['PubChem Compound Identifiers']
    ]

    # read in chembl ids based off of inchi id
    inchi_keys = pd.read_csv(
        './conversion/inchi_to_inchi_key_combined.csv')['InChI Key']
    inchis = pd.read_csv(
        './conversion/inchi_to_inchi_key_combined.csv')['InChI']
    chembl_ids = pd.read_csv(
        './conversion/inchi_key_to_chembl_combined.csv')['ChEMBL ID']

    inchi_to_chembl_dict = pd.Series(chembl_ids.values, index=inchis).to_dict()

    drugs_df['Chembl3'] = [
        inchi_to_chembl_dict[inchi] if inchi in inchi_to_chembl_dict else ''
        for inchi in drugs_df['InChI']
    ]
    drugs_df['InChI Key'] = inchi_keys

    drugs_df['Chembl ID'] = drugs_df.apply(lambda row: merge_chembls(
        row['Chembl1'], row['Chembl2'], row['Chembl3']),
                                           axis=1)

    return drugs_df


def get_drugs_df():
    """Returns a combined drugs data frame.

    Returns:
        Dataframe containg chemicals.tsv, drugs.tsv as well as Chembl ID and
        InChI Key information retreived from ./conversion/*.csv files.
    """
    chemicals_df = pd.read_csv('./raw_data/chemicals/chemicals.tsv', sep='\t')
    drugs_df = pd.read_csv('./raw_data/drugs/drugs.tsv', sep='\t')

    combined_df = drugs_df.append(chemicals_df, ignore_index=True)
    combined_df = combined_df.drop_duplicates()

    drugs_df = append_chembls(combined_df)
    drugs_df.fillna('', inplace=True)

    return drugs_df


def format_text_list(text_list):
    """Creates a formatted version of the given string according to MCF standards.

    This is used to format many columns from the drugs and genes dataframes like
    PubChem Compound Identifiers or NCBI Gene ID.

    Args:
        text_list: A single string representing a comma separated list. Some of
            the items are enlcosed by double quotes and some are not.

    Returns:
        A string that is mcf property text values list enclosed by double quotes
        and comma separated.

    Example:
        input: ('test1,
            "Carbanilic acid, M,N-dimethylthio-, O-2-naphthyl ester", "test2"')
        return: ('"test1",
             "Carbanilic acid, M,N-dimethylthio-, O-2-naphthyl ester", "test2"')
    """
    if not text_list:
        return ''
    formatted_str = ''
    joining = ''
    for prop_value in text_list.split(','):
        if prop_value.count('"') == 0 and joining:
            joining += prop_value + ','
        elif prop_value.count('"') == 0 or prop_value.count('"') == 2:
            formatted_str += '"' + prop_value.replace('"', '').strip() + '",'
        elif prop_value.count('"') == 1 and joining:
            formatted_str += joining.strip() + prop_value.replace('"',
                                                                  '') + '",'
            joining = ''
        elif prop_value.count('"') == 1:
            joining = prop_value + ','
        else:
            print('unexpected format: ' + text_list)
    return formatted_str.strip(',')


def format_semicolon_list(semi_list):
    """Formats a string representing a semi colon separated list into MCF
    property values list format.

    This is used to format 'PMIDs' in relationships.tsv.

    Args:
        semi_list: a string representing a semi colon separated list

    Returns:
        A string that is mcf property text values list enclosed by double quotes
        and comma separated.
    """
    if not semi_list:
        return ''
    formatted_str = ''
    for prop_value in semi_list.split(';'):
        formatted_str += '"' + prop_value + '",'
    return formatted_str.strip(',')


def format_bool(text, true_val):
    """Checks to see if given value matches the value that should return True.

    This is used to format the boolean values from 'PK' and 'PD' columns from
    relationships.tsv. For example, the values in 'PK' column are 'PK' if the
    relationship is pharmacokinetic, thus this function should return true only
    if the value is equal to 'PK'. We cannot conclude that a relationship is not
    pharmacokinetic by lack of 'PK' value, thus 'True' and empty are the only
    possible values.

    Args:
        text: the raw value that needs to be checked
        true_val: the value that 'text' should be to return true

    Returns:
        'True' (as a string) if 'text' matches 'true_val' and an empty string
        otherwise.
    """
    if text == true_val:
        return 'True'
    return ''


def get_enum(key_list, enum_dict):
    """Returns the mcf format of enum dcid list that represents a given value(s).

    Used to convert a list of values which map to enums to their appropriate
    enum dcid, as given by the enum_dict. For this import, enum_dict is either
    ASSOCIATION_ENUM_DICT or EVIDENCE_ENUM_DICT from config.py .

    Args:
        key_list: a string representing a comma-separated list of enum mapping
            values
        enum_dict: value to enum dcid mapping, each item of key_list should be a
            key

    Returns:
        a string representing a comma separated list of enum dcids with the 'dcid'
        context indentifier.
    """
    if not key_list:
        return ''
    formatted_enums = ''
    for key in key_list.split(','):
        formatted_enums += 'dcid:' + enum_dict[key] + ','
    return formatted_enums.strip(',')


def get_xref_mcf(xrefs, xref_to_label):
    """Returns the mcf format of a given string of xrefs.

    Convert a list of xrefs to their mcf format of <prop_label>: <prop_text_value>
    using the xref_to_label dict to lookup the property label of the given
    indentifier. For this import, xref_to_label is either GENE_XREF_PROP_DICT or
    DRUG_XREF_PROP_DICT from config.py .

    Args:
        xref: a string representing a comma-separated list of xrefs enclosed by
            double quotes
        xref_to_label: xref name in pahrmgkb to DC property label mapping

    Returns:
        a multiline mcf formatted string of all of the xrefs' prop labels + values
    """

    xref_mcf = ''
    if not xrefs:
        return ''
    for xref in xrefs.split(','):
        xref_pair = xref.replace('"', '').strip().split(':')
        if xref_pair[0] not in xref_to_label:
            print('unexpected format in gene xrefs:' + xrefs)
            continue
        prop_label = xref_to_label[xref_pair[0]]
        prop_value = ':'.join(xref_pair[1:]).strip()
        xref_mcf += prop_label + ': "' + prop_value + '"\n'
    return xref_mcf


def get_gene_dcids(symbol):
    """Returns the dcid of a gene created from the gene symbol. """

    if symbol:
        return ['bio/hg19_' + symbol, 'bio/hg38_' + symbol]
    return ''


def get_drug_dcid(row):
    """Returns dcid of a drug.

    If the chembl id of the drug was not found, then a new dcid for the drug is
    created based on the pharmGKB id.
    """

    if row['Chembl ID']:
        return 'bio/' + row['Chembl ID']
    return 'bio/' + row['PharmGKB Accession Id']


def get_compound_type(compound_types):
    """Returns mcf value format of the typeOf property for a compound.

    This is applied to the 'Type' entry of each row of drugs_df.

    Args:
        compound_types: string of comma separated list of type values

    Returns:
        If the compound is of a drug type, then typeOf value should be dcs:Drug
        Otherwise the typeOf should be dcid:ChemicalCompound
        If the list contains both drug types and non drug types, then the typeOf
        should be dcid:ChemicalCompound,dcid:Drug
    """

    drug_types = ['Drug', 'Drug Class', 'Prodrug']
    types = set()
    for compound_type in compound_types.split(','):
        compound_type = compound_type.replace('"', '').strip()
        if compound_type in drug_types:
            types.add('dcid:Drug')
        else:
            types.add('dcid:ChemicalCompound')
    if len(types) == 2:
        return 'dcs:ChemicalCompound,dcs:Drug'
    return types.pop()


def get_gene_mcf(row, gene_dcid):
    """Returns the mcf of gene node given its dcid and genes_df row information.

    Uses GENE_TEMPLATE from config.py, mcf_template_filler from DC data/util, and
    the values from the genes_df row to generate the mcf of a gene node. Helper
    methods such as format_text_list and get_xref_mcf are used to format the data.

    Args:
        row: a row from genes_df
        gene_dcid: dcid of the gene mcf node to be created

    Returns:
        An mcf formatted string of the gene node.
    """

    ncbi = format_text_list(row['NCBI Gene ID'])
    hgnc = format_text_list(row['HGNC ID'])
    ensembl = format_text_list(row['Ensembl Id'])
    alt_symb = format_text_list(row['Alternate Symbols'])

    templater = mcf_template_filler.Filler(config.GENE_TEMPLATE,
                                           required_vars=['dcid'])
    template_dict = {
        'dcid': gene_dcid,
        'name': row['Name'],
        'symbol': row['Symbol'],
        'pharm_id': row['PharmGKB Accession Id'],
        'ncbi_ids': ncbi,
        'hgnc_ids': hgnc,
        'ensembl_ids': ensembl,
        'alt_symbols': alt_symb,
    }
    # remove empty values from dict
    template_dict = {
        key: value for key, value in template_dict.items() if value
    }

    mcf = templater.fill(template_dict)
    mcf += get_xref_mcf(row['Cross-references'], config.GENE_XREF_PROP_DICT)

    return mcf


def write_gene_row(mcf_file, row, pharm_to_dcid):
    """Writes mcf formatted strings of a row from gene_df to file.

    Retreives the dcids for the gene symbol. Each row of gene_df represents two
    gene nodes in Data Commons because every one gene symbol yeilds two dcids.
    Stores the pharmgkb id to dcid mapping in pharm_to_dcid dictionary which will
    be used in parsing relationships.tsv. Then gets and writes the mcf string to
    file for each gene dcid.

    Args:
        f: output mcf file
        row: row from genes_df pandas DataFrame
        pharm_to_dcid: pharmgkb id to dcid of genes dictionary mapping
    """

    gene_dcids = get_gene_dcids(row['Symbol'])

    pharm_to_dcid[row['PharmGKB Accession Id']] = gene_dcids

    for gene_dcid in gene_dcids:
        mcf = get_gene_mcf(row, gene_dcid)
        mcf_file.write(mcf)


def get_drug_mcf(row, drug_dcid):
    """Returns the mcf of drug node given its dcid and drugs_df row information.

    Uses DRUG_TEMPLATE from config.py, mcf_template_filler from DC data/util, and
    the values from the drugs_df row to generate the mcf of a drug node. Helper
    methods such as format_text_list, get_compound_type, and get_xref_mcf are used
    to format the data.

    Args:
        row: a row from drugss_df
        drug_dcid: dcid of the drug mcf node to be created

    Returns:
        An mcf formatted string of the drug node.
  """

    trade = format_text_list(row['Trade Names'])
    rx_id = format_text_list(row['RxNorm Identifiers'])
    atc = format_text_list(row['ATC Identifiers'])
    pubchem = format_text_list(row['PubChem Compound Identifiers'])
    compound_type = get_compound_type(row['Type'])

    dc_name = drug_dcid.replace('bio/', '')

    templater = mcf_template_filler.Filler(config.DRUG_TEMPLATE,
                                           required_vars=['dcid', 'type'])
    template_dict = {
        'dcid': drug_dcid,
        'type': compound_type,
        'dc_name': dc_name,
        'name': row['Name'],
        'trade_names': trade,
        'smiles': row['SMILES'],
        'inchi': row['InChI'],
        'inchi_key': row['InChI Key'],
        'pharm_id': row['PharmGKB Accession Id'],
        'rx_ids': rx_id,
        'atc_ids': atc,
        'pubchem_compound_ids': pubchem,
    }
    template_dict = {
        key: value for key, value in template_dict.items() if value
    }

    mcf = templater.fill(template_dict)
    mcf += get_xref_mcf(row['Cross-references'], config.DRUG_XREF_PROP_DICT)

    return mcf


def write_drug_row(mcf_file, row, pharm_to_dcid):
    """Writes mcf formatted string of a row from drugs_df to file.

    Retreives the dcid for the drug row. Stores the pharmgkb id to dcid mapping
    in pharm_to_dcid dictionary which will be used in parsing relationships.tsv.
    Then gets and writes the mcf string to file for the drug dcid.

    Args:
        f: output mcf file
        row: row from drugs_df pandas DataFrame
        pharm_to_dcid: pharmgkb id to dcid of drugs dictionary mapping
    """

    drug_dcid = get_drug_dcid(row)
    pharm_to_dcid[row['PharmGKB Accession Id']] = drug_dcid

    mcf = get_drug_mcf(row, drug_dcid)

    mcf_file.write(mcf)


def get_relation_mcf(row, drug_dcid, gene_dcid):
    """Returns the mcf of ChemicalCompoundGeneAssociation node given the dcids of
    the drug and gene involved as well as the relations.tsv based row information.

    Uses RELATION_TEMPLATE from config.py, mcf_template_filler from DC data/util,
    and the values from the given dataframe row to generate the mcf. Helper
    methods such as format_semicolon_list, format_bool, and get_enum are used to
    format the data.

    Args:
        row: a row from either drug_gene_df or gene_drug_df
        drug_dcid: dcid of the drug node involved in the association
        gene_dcid: dcid of the gene node involved in the association

    Returns:
        An mcf formatted string of the ChemicalCompoundGeneAssociation node.
    """

    drug_ref = drug_dcid.replace('bio/', '')
    gene_ref = gene_dcid.replace('bio/', '')

    pubmed = format_semicolon_list(row['PMIDs'])
    pk_bool = format_bool(row['PK'], 'PK')
    pd_bool = format_bool(row['PD'], 'PD')
    assoc_enum = get_enum(row['Association'], config.ASSOCIATION_ENUM_DICT)
    evid_enum = get_enum(row['Evidence'], config.EVIDENCE_ENUM_DICT)

    templater = mcf_template_filler.Filler(
        config.RELATION_TEMPLATE,
        required_vars=['dcid', 'gene_dcid', 'drug_dcid'])
    template_dict = {
        'dcid': 'bio/CGA_' + drug_ref + '_' + gene_ref,
        'name': 'CGA_' + drug_ref + '_' + gene_ref,
        'gene_dcid': gene_dcid,
        'drug_dcid': drug_dcid,
        'pubmed_ids': pubmed,
        'pk_bool': pk_bool,
        'pd_bool': pd_bool,
        'assoc_enums': assoc_enum,
        'evid_enums': evid_enum,
    }
    template_dict = {
        key: value for key, value in template_dict.items() if value
    }

    mcf = templater.fill(template_dict)
    return mcf


def write_relation_row(mcf_file, row, drug_is_first, genes_pharm_to_dcid,
                       drugs_pharm_to_dcid):
    """Writes mcf string of a row from drug_gene_df or gene_drug_df to file.

    Determines the drug dcid and gene dcids, then retreives the
    ChemicalCompoundGeneAssociation mcf for each gene dcid and writes the mcf to
    the given file.

    Args:
        f: output mcf file
        row: a row from either drug_gene_df or gene_drug_df
        drug_is_first: boolean indicating if the pharmGKB id of the drug is
                       'Entity1_id' or 'Entity2_id'
        genes_pharm_to_dcid: pharmgkb id to dcids of gene dictionary mapping
        drugs_pharm_to_dcid: pharmgkb id to dcids of drug dictionary mapping
    """
    if drug_is_first:
        drug_pharm = row['Entity1_id']
        gene_pharm = row['Entity2_id']
    else:
        drug_pharm = row['Entity2_id']
        gene_pharm = row['Entity1_id']

    if drug_pharm not in drugs_pharm_to_dcid:
        print('unrecognized drug pharm id: ' + drug_pharm)
        return

    if gene_pharm not in genes_pharm_to_dcid:
        print('unrecognized gene pharm id: ' + gene_pharm)
        return

    drug_dcid = drugs_pharm_to_dcid[drug_pharm]
    gene_dcids = genes_pharm_to_dcid[gene_pharm]

    for gene_dcid in gene_dcids:
        mcf = get_relation_mcf(row, drug_dcid, gene_dcid)
        mcf_file.write(mcf)


def main():
    """Generates ./pharmgkb.mcf

    Downloads the related pharmgkb dataset files. Creates pandas DataFrames from
    each of the .tsv files:
        drugs_df - combined data from chemicals.tsv and drugs.tsv
        genes_df - data from genes.tsv
        relation_df - data from relationships.tsv
    Then parses drugs and genes data frames, writing the nodes and saving their
    pharmgkb id to dcid mappings. These mappings are used when parsing the
    relationships.tsv based data frames. The dataframe, relation_df is filtered
    into two dataframes:
        drug_gene_df - 'Entity1_type' is 'Chemical' and 'Entity2_type' is 'Gene'
        gene_drug_df - 'Entity1_type' is 'Gene' and 'Entity2_type' is 'Chemical'
    This makes it easy to parse the drug-gene association based rows since the
    types and order of the types are established.
    """
    download_pharmgkb_datasets()

    mcf_file = open('pharmgkb.mcf', 'w')

    genes_pharm_to_dcid = {}
    genes_df = pd.read_csv('./raw_data/genes/genes.tsv', sep='\t')
    genes_df.fillna('', inplace=True)
    print('writing gene nodes to mcf....')
    genes_df.apply(
        lambda row: write_gene_row(mcf_file, row, genes_pharm_to_dcid), axis=1)

    drugs_pharm_to_dcid = {}
    drugs_df = get_drugs_df()
    print('writing drug nodes to mcf....')
    drugs_df.apply(
        lambda row: write_drug_row(mcf_file, row, drugs_pharm_to_dcid), axis=1)

    relation_df = pd.read_csv('./raw_data/relationships/relationships.tsv',
                              sep='\t')
    relation_df.fillna('', inplace=True)

    print('writing ChemicalCompoundGeneAssociation nodes to mcf....')

    drug_gene_df = relation_df[(relation_df['Entity1_type'] == 'Chemical') &
                               (relation_df['Entity2_type'] == 'Gene')]
    drug_first = True
    drug_gene_df.apply(lambda row: write_relation_row(
        mcf_file, row, drug_first, genes_pharm_to_dcid, drugs_pharm_to_dcid),
                       axis=1)

    gene_drug_df = relation_df[(relation_df['Entity1_type'] == 'Gene') &
                               (relation_df['Entity2_type'] == 'Chemical')]
    drug_first = False
    gene_drug_df.apply(lambda row: write_relation_row(
        mcf_file, row, drug_first, genes_pharm_to_dcid, drugs_pharm_to_dcid),
                       axis=1)

    mcf_file.close()


if __name__ == '__main__':
    main()
