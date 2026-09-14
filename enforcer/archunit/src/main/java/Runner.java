import com.tngtech.archunit.core.domain.JavaClasses;
import com.tngtech.archunit.core.importer.ClassFileImporter;
import com.tngtech.archunit.lang.ArchRule;
import com.tngtech.archunit.lang.EvaluationResult;

import java.util.List;
import java.util.Map;

/** Evaluate every generated rule against compiled classes: exit 0 pass, 1 violation, 2 error. */
public final class Runner {

    public static void main(String[] args) {
        if (args.length == 0) {
            System.err.println("usage: java -jar enforcer-archunit.jar <classes-dir> ...");
            System.exit(2);
        }

        JavaClasses classes = new ClassFileImporter().importPaths(args);
        System.out.printf("%d classes imported from %s%n", classes.size(), String.join(", ", args));
        if (classes.size() == 0) {
            System.err.println("no classes imported -- is the project built?");
            System.exit(2);
        }

        // BUILDING a rule can throw too, and nothing thrown while building is a finding about the code.
        Map<String, ArchRule> generated;
        try {
            generated = GeneratedRules.rules();
        } catch (Throwable error) {
            System.out.println("ERROR      <rule construction>  " + error);
            System.exit(2);
            return;
        }

        boolean violated = false;
        boolean errored = false;
        for (Map.Entry<String, ArchRule> entry : generated.entrySet()) {
            String id = entry.getKey();
            try {
                EvaluationResult result = entry.getValue().evaluate(classes);
                List<String> details = result.getFailureReport().getDetails();
                if (details.isEmpty()) {
                    System.out.println("PASS       " + id);
                } else {
                    violated = true;
                    System.out.println("VIOLATION  " + id + "  " + details.size() + " violation(s)");
                    for (String detail : details) {
                        System.out.println("             " + detail);
                    }
                }
            } catch (Throwable error) {
                // The rule reported nothing about the code -- never a pass, and never a violation.
                errored = true;
                System.out.println("ERROR      " + id + "  " + error);
            }
        }
        System.exit(errored ? 2 : violated ? 1 : 0);
    }

    private Runner() {
    }
}
