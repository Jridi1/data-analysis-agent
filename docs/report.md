# Fraud detection under temporal drift: analysis report

## Summary

This report analyzes a synthetic payments dataset of 400,000 transactions from 2023, where fraud becomes more common from July. A logistic regression, trained on all of the training file and scored once on the sealed October to December test file, reached PR-AUC 0.369885 and ROC AUC 0.843889, about 18.6 times the PR-AUC of random guessing. Flagging the top 2% of scores caught 819 of the 1,983 frauds (recall 0.413011) at precision 0.410115. The model relies mostly on two velocity features, txn_count_24h and failed_txn_count_24h. After June, fraud moved toward smaller amounts, international transactions and denser velocity, and the model held up on the test quarter. Its main blind spot is fraud with 3 or fewer transactions in 24 hours (224 frauds in months 8 and 9, none caught), which may be mostly label noise. Two choices matter for trust: post_auth_risk_score was excluded because it leaks the target, and the final model uses no class weight so its probabilities stay usable.

## Dataset and integrity

* Train: 300,113 rows, 21 columns, 0 nulls, 0 duplicated transaction_id, 0 impossible values, sorted by time. 39,983 customers and 8,000 merchants.
* Train fraud: 4,871 frauds, rate 0.016231. Test fraud: 1,983 frauds out of 99,887, rate 0.019852.
* amount_deviation_from_user_mean goes down to minus 778.6, which is normal for that column.
* Monthly train fraud rate (transactions, frauds, rate): January 33881, 476, 0.014049. February 31006, 457, 0.014739. March 34288, 531, 0.015486. April 32827, 512, 0.015597. May 34042, 476, 0.013983. June 32950, 462, 0.014021. July 34023, 675, 0.019840. August 34207, 657, 0.019207. September 32889, 625, 0.019003.
* Drift: the rate steps from 1.40% in June to 1.98% in July, a rise of 0.58 points that persists.

## Leakage check

* post_auth_risk_score: legit rows mean 0.200331, min 0.000001, max 0.400000. Fraud rows mean 0.851771, min 0.700048, max 0.999861. ROC AUC alone: 1.0. The classes never overlap, so the column leaks the target and was excluded from every model.
* Also excluded: all ID columns, transaction_time and any column derived from it.

## Feature signal

* ROC AUC of each feature alone: txn_count_24h 0.800296, failed_txn_count_24h 0.612666, is_international 0.538415, merchant_risk_score 0.530556, ip_risk_score 0.527707, txn_count_1h 0.511886, kyc_level 0.505682, geo_distance_from_last_txn 0.502997, credit_score_band 0.500858, account_age_days 0.498409, avg_monthly_spend 0.493597, amount_deviation_from_user_mean 0.479208, transaction_amount 0.478680.
* Fraud rate by txn_count_24h: about 0.5% for 0 to 3 transactions, 0.8514% at 4, 1.5897% at 5, 3.5784% at 6, 8.4571% at 7, 20.0% at 8, 40.3141% at 9, 62.7968% at 10.
* Fraud rate by failed_txn_count_24h: 1.1684% at 0, 2.1847% at 1, 4.6883% at 2, 9.4095% at 3, 20.1835% at 4.
* International fraud rate 3.3971% against 1.4913% domestic. Payment channel, device, KYC level and credit band are flat (1.57% to 1.67%).
* Lowest amount quintile: fraud rate 1.96%, against 1.48% to 1.61% in the other four.

## Drift inside the train data

* Feature ROC AUC, months 1 to 6 then months 7 to 9: transaction_amount 0.503 then 0.442. amount_deviation_from_user_mean 0.504 then 0.443. is_international 0.518 then 0.569. txn_count_24h 0.789 then 0.818. All other shifts are 0.017 or smaller.
* Fraud rate for domestic transactions: 0.014095 then 0.016521. International: 0.022030 then 0.057437.
* Fraud rate by txn_count_24h bucket, months 1 to 6 then 7 to 9: 0 to 3: 0.005408 then 0.005777. 4 to 5: 0.009653 then 0.014853. 6 to 7: 0.042475 then 0.067515. 8 and more: 0.276522 then 0.335491.
* Median amount, fraud rows: 2071.907611 then 1725.324516. Legit rows: 2019.425605 then 2016.891943.
* Share of rows at or below the 10th percentile of amounts, fraud rows: 0.101235 then 0.196219. Legit rows: 0.099230 then 0.099595.
* The average values of legit transactions did not change on any feature. Only the way fraud looks changed: smaller amounts, more international, denser velocity.

## Validation design

* Model selection: train months 1 to 6, validate months 7 to 9. Later tuning: train months 1 to 7, validate months 8 and 9. The test file stayed sealed. Primary metric PR-AUC (average precision), then ROC AUC.

## Model comparison

* Random guessing PR-AUC 0.019353 (the validation fraud rate, 1957 frauds in 101119 rows).
* txn_count_24h alone: PR-AUC 0.208514, ROC AUC 0.817779.
* Logistic regression, class_weight balanced: PR-AUC 0.320742, ROC AUC 0.838228.
* HistGradientBoosting, default settings: PR-AUC 0.284549, ROC AUC 0.823677. It overfits (independent check: train PR-AUC 0.374).
* Logistic regression by month: July PR-AUC 0.348740, ROC AUC 0.839789. August 0.303257, 0.832082. September 0.310689, 0.843037. No decay (independent check: monthly noise about 0.02 PR-AUC).

## Improvement and final model

* Added features, PR-AUC on months 7 to 9 (baseline 0.320742): intl_x_velocity (is_international times txn_count_24h) 0.333434, kept. low_amount 0.321960. amount_to_spend 0.320160. failed_ratio 0.318918. txn_hinge 0.311953 (worse). All five together 0.325560.
* Recency test, evaluated on months 8 and 9: months 1 to 6 without low_amount 0.318570. Months 1 to 7 without low_amount 0.326900. Months 1 to 6 with low_amount 0.319564. Months 1 to 7 with low_amount 0.334243. Recent data and the low_amount flag help together.
* Tuning: logistic regression C from 0.01 to 10 gives PR-AUC 0.334243 to 0.334304, so C does not matter. Boosting reached 0.307212 (early stopping made its settings identical; independent check: best 0.311, never above logistic regression).
* Final choice: logistic regression, C 1, no class weight, 15 numeric features (13 original plus intl_x_velocity and low_amount) plus one hot payment_channel and device_type, trained on all of train.

## Calibration and review budget

* Balanced model: PR-AUC 0.334243, Brier 0.151558. Unweighted model: PR-AUC 0.329202, Brier 0.015747. Always predicting the train fraud rate: Brier 0.018756. Class weighting inflates probabilities, so the final model uses no class weight.
* Review budget with the balanced model: top 0.5% (336 flagged) caught 227 frauds, precision 0.675595, recall 0.177067. Top 1% (671) caught 347, precision 0.517139, recall 0.270671. Top 2% (1342) caught 502, precision 0.374069, recall 0.391576.
* Best F1 for the balanced model: threshold 0.82, F1 0.384676, precision 0.385580, recall 0.383775.

## Final test result

* PR-AUC 0.369885, ROC AUC 0.843889, Brier 0.015846. PR-AUC is about 18.6 times the test fraud rate (independent check).
* Top 2% of scores (1997 flagged): 819 frauds caught, precision 0.410115, recall 0.413011.
* Top 1% of scores: precision 0.577154, recall 0.290469.
* Probability threshold 0.12: share flagged 0.020864, precision 0.400672, recall 0.421079, F1 0.410622.
* By month: October 34090 rows, 654 frauds, PR-AUC 0.357836, ROC AUC 0.849141. November 32839 rows, 675 frauds, PR-AUC 0.385057, ROC AUC 0.847637. December 32958 rows, 654 frauds, PR-AUC 0.367367, ROC AUC 0.834744. No decay over the test quarter (independent check: monthly noise about 0.022 PR-AUC).
* No drop against validation, so the 20% drop rule was not triggered. Possible reasons: three post drift months in training instead of one, and a higher fraud rate.

## Interpretation

* Permutation importance (drop in PR-AUC, months 8 and 9): txn_count_24h 0.301528, failed_txn_count_24h 0.107329, intl_x_velocity 0.031802, merchant_risk_score 0.009558, low_amount 0.008255, is_international 0.004137, ip_risk_score 0.004120, txn_count_1h 0.001519, avg_monthly_spend 0.000540, credit_score_band 0.000244. The model baseline is 0.329202, so txn_count_24h carries about 92% of it (independent check).
* Standardized coefficients, model on months 1 to 6 then model on months 7 to 9: low_amount 0.001666 then 0.283201. txn_count_1h 0.020375 then 0.142100. txn_count_24h 1.237698 then 1.328341. intl_x_velocity 0.092163 then 0.217101. merchant_risk_score 0.132429 then 0.157926. ip_risk_score 0.107081 then 0.122620. failed_txn_count_24h 0.471242 then 0.483447. Clear changes (independent bootstrap): low_amount and txn_count_1h.
* Recall of the top 2% rule by group (months 8 and 9): bank_transfer 0.317757, card 0.381317, upi 0.411243, wallet 0.391304. desktop 0.369822, mobile 0.393461, tablet 0.350877. Domestic 0.357905, international 0.498008. Differences by channel and device are within noise.
* Recall by txn_count_24h bucket: 0 to 3 transactions: 0.000000 (224 frauds, 1 transaction flagged). 4 to 5: 0.050676. 6 to 7: 0.394541. 8 and more: 0.891365.
* Recall by amount quintile (quintile 1 is the lowest amounts): 0.369620, 0.390909, 0.343750, 0.395455, 0.439462. No amount blind spot.
* Of the 788 missed frauds, 95% have 7 or fewer transactions in 24 hours (independent check).

## Limitations

* The data is synthetic and was generated from a logistic model, which favors linear models. Real payment data would be messier.
* Documented label noise of up to 0.5% limits any model. The 224 frauds with 3 or fewer transactions in 24 hours (fraud rate 0.55%) may be mostly noise.
* Probabilities lag the rising fraud rate (independent check: mean predicted 1.52% against actual 1.91% on validation), so a production system needs regular recalibration.
* Features and settings were chosen on the validation months, which leaves a small selection bias. The test file was used once and no decision changed afterwards.
* One model family was tuned in depth. Boosting was only lightly tuned.

## Recommendations

* Use the logistic regression with the 15 numeric features and flag the top 2% of scores as the operating rule. A flagged share is likely to transfer better than a probability threshold when the model is retrained.
* Retrain on recent months regularly, because the fraud pattern moves and the low_amount signal only exists after the drift.
* Add signals beyond transaction velocity, for example customer history, to reach low velocity fraud.
* Recalibrate probabilities on recent data before using them for risk based decisions.
