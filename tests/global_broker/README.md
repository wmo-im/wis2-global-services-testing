# WIS2 Global Broker Functional PyTest Script

## Overview

This PyTest script implements the functional tests for the Global Broker.  **Currently a "work in progress".**

### Outstanding Issues

1. Evaluation of the Global Broker metrics specified in the [Global Broker Testing Document.](https://github.com/wmo-im/wis2-global-services-testing/blob/main/global-services-testing/sections/testing/global-broker.adoc) 
2. PyTest exception handling and job control

### Environment Configurables

1. SCENARIO_BROKER: Scenario Message Generator
2. GLOBAL_BROKER: Optional Client Subscription Connection: "gb.wis2dev.io"
3. TEST_BROKER_CLEAR: "1883" Cleartext Connection
4. TEST_BROKER_TLS: "8883" TLS/SSL Connection
5. TEST_BROKER_WS: "443" Websockets Connection
6. TEST_BROKER_TEST: Functional Tests Connections
7. TEST_PACE: Extends the delay between tests.
8. MESSAGE_PACE: Extends the delay between MQTT client events like subscribing and publishing.

### Test Roster

All of the specified Global Broker tests are performed, however there are more tests in the PyTest script than outlined in the [Global Broker Testing Document.](https://github.com/wmo-im/wis2-global-services-testing/blob/main/global-services-testing/sections/testing/global-broker.adoc) 

#### Test 1: Global Broker Clear-Text Connectivity

A clear text connection attempt to confirm that the Global Broker under test is up and ready to go.  Useful for debugging.

#### Test 2: Global Broker TLS Connectivity

TLS and WebSocket tests are separated to avoid exeption handling in PyTest.  As outlined, either a TLS or WebSocket connection is sufficient for the encrpyted transport test to pass.  However exception hanling in PyTest frustrates implementing a sigle test that can pass with one of the two conditions failing.

#### Test 3: Global Broker WS Connectivity

The WebSocket case since either a TLS or WebSocket connection is sufficient for the specified test to pass.  Future updates to resolve the PyTest exception handling issue and allow one of two conditions to fail and maintaining a passing test.

#### Test 4: Global Broker TLS Certifiate Validity

Again, the Certificat Validity tests are separated to avoid exeption handling in PyTest.

#### Test 5: Global Broker WS Certificate Validity

The WebSocket case since either a TLS or WebSocket certificate validation is sufficient for the specified test to pass.

#### Test 6: Global Broker Subscription Read Access

A simple high level topic subscritpion to the "live" Global Broker under test.  No message generation is performed.  Test message generation may be necessary if the Global Broker under test is configured in an isolated environment.

#### Test 7: Global Broker Write Access

A publication attempt to a valid WIS2 topic on the Global Broker under test to evaluate the world accessible "everyone:everyone" permissions.  Exception hanling in PyTest frustrates implementing this test since a successful outcome involves the client violating the permissions policy prompting an MQTT client disconnect.  Future updates to resolve this issue

#### Test 8: WIS2 Broker Antiloop Test

Publishing multiple messages with identical UUIDs using the Scenario Broker.

#### Test 9: WIS2 Node Invalid Centre ID Test

Publishing messages from a Centre-ID that does not match the Centre-ID in the topic using the Scenario Broker

#### Test 10: WIS2 GB Valid Topic Test

Publishing messages to Valid Topics using the Scenario Broker.  The script cycles through this list of valid topics:

- origin/a/wis2/io-wis2dev-12-test/metadata
- origin/a/wis2/io-wis2dev-12-test/metadata/core/weather/surface-based-observations/synop
- origin/a/wis2/io-wis2dev-13-test/data/core/weather/aviation/metar
- origin/a/wis2/io-wis2dev-13-test/data/core/weather/surface-based-observations/synop
- origin/a/wis2/io-wis2dev-14-test/data/core/weather/surface-based-observations/ship-hourly
- origin/a/wis2/io-wis2dev-14-test/data/core/weather/space-based-observations/sentinel-2b/msi
- origin/a/wis2/io-wis2dev-15-test/data/core/weather/space-based-observations/swot/poseidon-3c
- origin/a/wis2/io-wis2dev-15-test/data/core/space-weather/space-based-observations/xmm-newton/epic
- origin/a/wis2/io-wis2dev-16-test/data/core/space-weather/space-based-observations/themis-a/scm
- origin/a/wis2/io-wis2dev-16-test/data/core/weather/prediction/analysis/nowcasting/deterministic/global
- origin/a/wis2/io-wis2dev-17-test/data/core/weather/prediction/analysis/seasonal/deterministic/global
- origin/a/wis2/io-wis2dev-17-test/data/core/climate/surface-based-observations/monthly
- origin/a/wis2/io-wis2dev-18-test/data/core/climate/surface-based-observations/daily
- origin/a/wis2/io-wis2dev-18-test/data/core/cryosphere/experimental
- origin/a/wis2/io-wis2dev-19-test/data/core/cryosphere/experimental/graviton/lambda
- origin/a/wis2/io-wis2dev-19-test/data/core/hydrology/experimental
- origin/a/wis2/io-wis2dev-20-test/data/core/hydrology/experimental/turbulent/laminar/flows
- origin/a/wis2/io-wis2dev-20-test/data/core/atmospheric-composition/experimental
- origin/a/wis2/io-wis2dev-13-test/data/core/atmospheric-composition/experimental/smog/tests
- origin/a/wis2/io-wis2dev-15-test/data/core/ocean/surface-based-observations/drifting-buoys
- origin/a/wis2/io-wis2dev-19-test/data/core/ocean/surface-based-observations/sea-ice

#### Test 11: WIS2 GB Valid Message Test

Publishing valid messages to valid topics using the Scenario Broker.  A repeat of Test 10.  Future updates that evaluate the implementation might require changes that differentiate this test from test number 10.

#### Test 12: WIS2 GB Inalid Topic Test

Publishing messages to Invalid Topics using the Scenario Broker.  The script cycles through this list of invalid topics:

- origin/a/wis2/io-wis2dev-14-test/data
- origin/a/wis2/io-wis2dev-14-test/data/core
- origin/a/wis2/io-wis2dev-14-test/data/core/weather/surface-based-observations
- origin/a/wis3/io-wis2dev-14-test/data/core/weather/surface-based-observations/synop
- origin/a/wis2/io-wis2dev-14-test/data/core/weather/surface-sed-observations/synop
- origin/a/wis3/io-wis2dev-14-test/data/core/weather/surface-based-observations/synop
- origin/a/wis2/io-wis2dev-14-test/database/core/weather/surface-based-observations/synop
- origin/a/wis2/io-wis2dev-14-test/data/core/weather/surface-based-observations/synop/prediction
- origin/a/wis2/io-wis2dev-14-test/data/core/weather/space-based-observations/smm-newton/epic
- origin/a/wis2/io-wis2dev-14-test/data/core/weather/space-based-observations/themis-a/scm
- origin/a/wis2/io-wis2dev-14-test/data/core/space-weather/space-based-observations/sentinel-2b/msi
- origin/a/wis2/io-wis2dev-14-test/data/core/space-weather/space-based-observations/swot/poseidon-3c
- origin/a/wis2/io-wis2dev-14-test/data/core/geospatial/surface-based-observations/synop
- origin/a/wis2/io-wis2dev-14-test/data/core/ibweather/surface-based-observations/dynop
- origin/a/wis2/io-wis2dev-14-test/data/core/atmospheric-composition/satellite
- origin/a/wis2/io-wis2dev-14-test/data/core/atmospheric-composition
- origin/a/wis2/io-wis2dev-14-test/data/core/weather/prediction
- origin/a/wis2/io-wis2dev-14-test/data/core/weather/prediction/analysis
- origin/a/wis2/io-wis2dev-14-test/data/core/weather/prediction/analysis/nowcasting
- origin/a/wis2/io-wis2dev-14-test/data/core/weather/prediction/hindcast
- origin/a/wis2/io-wis2dev-14-test/data/core/weather/prediction/hindcast/short-range
- origin/a/wis2/io-wis2dev-14-test/data/core/weather/prediction/hindcast/nowcasting

#### Test 13: WIS2 GB Inalid Message Test

Publishing Invalid Messages using the Scenario Broker.  The script cycles through the list of [Invalid Message Scenarios](https://github.com/wmo-im/wis2-global-services-testing/tree/main/tools/Documentation/scenario)
