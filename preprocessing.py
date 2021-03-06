import pandas as pd
import numpy as np

import pycountry, pycountry_convert

import json

def get_continent(row):
    """ retrieve the continent data for a given row """
    
    if row['Country Name'] in ['Bahamas, The', 'Curacao', 'Sint Maarten (Dutch part)', 'St. Kitts and Nevis', 'St. Lucia', 'St. Martin (French part)', 'St. Vincent and the Grenadines', 'Virgin Islands (U.S.)']:
        return 'NA'
    elif row['Country Name'] in ['Channel Islands','Czech Republic','Faeroe Islands','Kosovo','Macedonia, FYR','Moldova','Slovak Republic']:
        return 'EU'
    elif row['Country Name'] in ['Hong Kong SAR, China', 'Iran, Islamic Rep.', 'Korea, Dem. Rep.', 'Korea, Rep.', 'Kyrgyz Republic', 'Lao PDR','Macao SAR, China', 'Micronesia, Fed. Sts.','Timor-Leste','Vietnam', 'West Bank and Gaza', 'Yemen, Rep.']:
        return 'AS'
    elif row['Country Name'] in ['Congo, Dem. Rep.', 'Congo, Rep.', "Cote d'Ivoire", 'Egypt, Arab Rep.', 'Tanzania', 'Gambia, The']:
        return 'AF'
    elif row['Country Name'] in ['Bolivia', 'Venezuela, RB']:
        return 'SA'
    else:
        return pycountry_convert.country_alpha2_to_continent_code(pycountry.countries.get(name = row['Country Name']).alpha_2)

def preprocess_continents(training_set):
        """Preprocess the data while adding in continent and region in order to better interpolate missing data and improve models."""
        
        X = training_set.copy()
        
        X['continent'] = X.apply(lambda row: get_continent(row),axis=1)
        
        return X

def preprocess_with_continent_interpolation(training_set, submit_rows_index, years_ahead=1):
    """Preprocess the training set to get the submittable training rows
    with continent-indicator-year averages filled in for missing data. These
    averages come from the ind_yr_cont_avgs.json file
    """
    X_with_cont = preprocess_continents(training_set)
    X_submit = X_with_cont.loc[submit_rows_index]

    def rename_cols(colname):
        if colname not in ['Country Name', 'Series Code', 'Series Name', 'continent']:
            return int(colname.split(' ')[0])
        else:
            return colname
    X = X_submit.rename(rename_cols, axis=1)

    with open("ind_yr_cont_avgs.json", "r") as content:
        cont_avgs = json.load(content)

    def impute_indyrcontavg(r, ind, cont):
        if pd.isna(r['value']):
            r['value'] = cont_avgs[str((ind, cont, r.name))]
            return(r)
        else:
            return(r)

    for ix,row in X.iterrows():
        ind = row['Series Code']
        cont = row['continent']
        df = row.to_frame(0)
        df.columns = ['value']
        df = df.apply(impute_indyrcontavg, axis = 1, args=(ind,cont))
        X.loc[ix] = df['value']
    # we only want the time series data for each row
    X = X.iloc[:, :-4]

    # Split prediction and target
    Y = X.iloc[:, -1]  # 2007
    X = X.iloc[:, :-1*years_ahead]  # 1972:2006 (if years_ahead==1)

    return X, Y

def preprocess_simple(training_set, submit_rows_index, years_ahead=1):
    """Preprocess the data for preliminary model building.

    This creates a training set where each row is a time series of a
    specific macroeconomic indicator for a specific country. The `X` table
    includes the time series from 1972 to 2006, and the 'Y' table includes
    the time series values for 2007. Missing values are coded as NaNs.

    X and Y only include rows for which we need to make submissions for the
    competition. Future iterations will include more rows to use as
    features.

    years_ahead: the number of years between data and the prediction target.

    Returns:
       X (pd.DataFrame): features for prediction
       Y (pd.Series): targets for prediction
    """
    # Select rows for prediction only
    X = training_set.loc[submit_rows_index]

    # Select and rename columns
    X = X.iloc[:, :-3]
    X = X.rename(lambda x: int(x.split(' ')[0]), axis=1)

    # Split prediction and target
    Y = X.iloc[:, -1]  # 2007
    X = X.iloc[:, :-1*years_ahead]  # 1972:2006 (if years_ahead==1)

    return X, Y

def preprocess_for_viz(training_set, submit_rows_index):
    """Preprocess the data for visualization.

    Selects rows for prediction and renames columns.
    """

    # Select rows for prediction only
    X = training_set.loc[submit_rows_index]

    # Select and rename columns
    yrs = X.iloc[:, :-3]
    names = X.iloc[:, -3:]
    yrs = yrs.rename(lambda x: int(x.split(' ')[0]), axis=1)

    df = pd.concat([yrs, names], axis=1)
    gb = df.groupby('Series Name')

    return gb

def preprocess_avg_NANs(training_set, submit_rows_index, years_ahead=1):
    """
    For NANs in most recent time period, takes average of all most recent series values with the same indicator name,
        or if there was a non NAN value in the most recent 10 years we take the most recent one  
        
    Also linearly interpolates the rest of the values in the dataframe

    Returns:
       X (pd.DataFrame): features for prediction
       Y (pd.Series): targets for prediction
    """

    # Select rows for prediction only
    full_training_rows = training_set.loc[submit_rows_index]

    # Select and rename columns
    X = full_training_rows.iloc[:, :-3]
    X = X.rename(lambda x: int(x.split(' ')[0]), axis=1)

    # Split prediction and target
    Y = X.iloc[:, -1]  # 2007
    X = X.iloc[:, :-1*years_ahead]  # 1972:2006
    
    indicators=np.unique(full_training_rows['Series Name'])
    last_column_train=X.iloc[:, -1]
    last_column_all=training_set.iloc[:,-5]
    for ind in indicators:
        
        # Find which rows in the training set and full dataset are for the indicator of interest  
        training_rows_with_indicator = last_column_train.loc[full_training_rows['Series Name'] == ind]
        all_rows_with_indicator = last_column_all.loc[training_set['Series Name'] == ind]
        
        # Find rows in training set that correspond to indicator of interest and have NAN values in most recent time period  
        NAN_training_indices_with_indicator = training_rows_with_indicator[training_rows_with_indicator.isnull()].index 
        median_of_others = np.median(all_rows_with_indicator[~all_rows_with_indicator.isnull()])
        
        # For series we need to replace NANs in, if there's a non-NAN value in the most recent 10 years we take the most recent one
        # Otherwise, we replace the value with the mean from all the time series corresponding to the same indicator
        for i in NAN_training_indices_with_indicator:
            X[X.columns[-1]][i] = median_of_others
            
            for recent_index in np.arange(2,10):
                recent_val = X[X.columns[-recent_index]][i]
                
                if not(np.isnan(recent_val)):
                    X[X.columns[-1]][i]=recent_val
                    break
    
    
    for index, row in X.iterrows():
        # Fill in gaps with linear interpolation
        row_interp = row.interpolate(
            method = 'linear', limit = 50,
            limit_direction = 'backward')
        X.loc[index]=row_interp.values
        
    return X, Y
